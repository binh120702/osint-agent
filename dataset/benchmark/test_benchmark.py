import unittest
import sys
import json
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from .loader import load_case
from .replay import SourceReplay
from .scoring import score_case
from .case_quality import audit
from .runner import _report_output
from .report_adapter import adapt_report_output
from .blind import blind_case, blind_prompt


class BenchmarkFrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_case("case_001")

    def test_blind_case_withholds_ground_truth_and_contract_prompt(self):
        public = blind_case(self.case.data)
        self.assertNotIn("ground_truth", public)
        self.assertNotIn("supports_findings", json.dumps(public))
        self.assertNotIn("FIND-001", json.dumps(public))
        self.assertNotIn("relations", public)
        self.assertNotIn("key_findings", public)
        self.assertNotIn("REQUIRED", blind_prompt(public))
        self.assertNotIn("CANONICAL", blind_prompt(public))
        self.assertEqual(public["case_id"], self.case.case_id)
        self.assertEqual(public["sources"], blind_case(self.case.data)["sources"])

    def test_case_loads_and_hashes(self):
        self.assertEqual(self.case.case_id, "OSINT-001")
        self.assertEqual(len(self.case.data["ground_truth"]["entities"]), 25)
        self.assertEqual(len(self.case.sha256), 64)

    def test_offline_replay_only_returns_case_sources(self):
        replay = SourceReplay(self.case.data)
        result = replay.search("3CX Mandiant")
        self.assertIn("SRC-", result)
        self.assertIn(self.case.data["sources"][0]["uri"], result)
        self.assertIn("source is not present", replay.fetch("https://not-in-case.test").lower())

    def test_offline_replay_normalizes_source_urls(self):
        replay = SourceReplay(self.case.data)
        source = self.case.data["sources"][0]
        self.assertIn('"success": true', replay.fetch(source["uri"] + "/").lower())

    def test_perfect_entity_and_relation_graph_scores_one(self):
        expected = self.case.data["ground_truth"]
        output = {
            "entities": expected["entities"],
            "relations": expected["relations"],
            "contradictions": expected.get("contradictions", []),
            "key_findings": expected["key_findings"],
            "reasoning_steps": [step["step_index"] for step in expected.get("reasoning_proof_chains", [])],
            "source_references": [source["source_id"] for source in self.case.data["sources"]],
        }
        scores = score_case(self.case.data, output)
        self.assertEqual(scores["entities"]["f1"], 1.0)
        self.assertEqual(scores["relations"]["f1"], 1.0)
        self.assertEqual(scores["contradictions"]["f1"], 1.0)
        self.assertEqual(scores["reasoning_coverage"]["ratio"], 1.0)

    def test_structured_report_annotations_are_scored(self):
        output = {
            "report": "Evidence shows the claim. " * 30,
            "claims": [{"claim": "claim", "source_references": ["SRC-001"]}],
            "key_findings": [{"question": self.case.data["ground_truth"]["key_findings"][0]["question"], "answer": self.case.data["ground_truth"]["key_findings"][0]["answer"], "supporting_entities": self.case.data["ground_truth"]["key_findings"][0]["supporting_entities"], "source_references": ["SRC-001"]}],
            "reasoning_steps": [],
            "contradictions": [],
            "available_source_references": ["SRC-001"],
            "structured_output_valid": True,
        }
        scores = score_case(self.case.data, output)
        self.assertEqual(scores["source_traceability"]["claim_level"]["ratio"], 1.0)
        self.assertGreater(scores["key_findings"]["f1"], 0.0)
        self.assertLess(scores["report_quality"]["score"], 1.0)

    def test_report_adapter_normalizes_case_aliases_without_inventing_values(self):
        parsed = {
            "key_findings": [{"question": "q", "answer": "a", "entities": ["3CX"], "sources": ["https://example.org/not-in-case"]}],
            "claims": [], "contradictions": [], "reasoning_step_details": [], "reasoning_steps": [],
        }
        adapted = adapt_report_output(self.case, parsed)
        self.assertEqual(adapted["key_findings"][0]["supporting_entities"], ["ENT-001"])
        self.assertEqual(adapted["key_findings"][0]["source_references"], ["https://example.org/not-in-case"])

    def test_report_adapter_recovers_legacy_finding_alias_and_unique_question(self):
        expected = self.case.data["ground_truth"]["key_findings"][0]
        adapted = adapt_report_output(self.case, {"key_findings": [{"finding": expected["answer"]}], "contradictions": []})
        self.assertEqual(adapted["key_findings"][0]["answer"], expected["answer"])
        self.assertEqual(adapted["key_findings"][0]["question"], expected["question"])


        parsed = {"key_findings": [], "claims": [], "contradictions": [], "reasoning_steps": [],
                  "reasoning_step_details": [{"step": "STEP 1", "entities": ["3CX"], "relations": ["made_up"], "conclusion": "x"}]}
        adapted = adapt_report_output(self.case, parsed)
        self.assertEqual(adapted["reasoning_step_details"][0]["id"], 1)
        self.assertEqual(adapted["reasoning_step_details"][0]["premise_entities"], ["ENT-001"])
        self.assertEqual(adapted["reasoning_step_details"][0]["premise_relations"], ["made_up"])

    def test_json_report_payload_is_parsed_and_completeness_is_explicit(self):
        report = "Report\n```json\n" + __import__("json").dumps({
            "findings": [], "claims": [], "reasoning_steps": [], "contradictions": []
        }) + "\n```"
        parsed = _report_output(self.case, report)
        self.assertTrue(parsed["structured_output_complete"])
        self.assertTrue(parsed["structured_output_valid"])

    def test_required_question_prompt_is_explicit(self):
        from dataset.benchmark import runner
        import inspect
        source = inspect.getsource(runner.run_existing_agent)
        self.assertIn("one finding object for EVERY required case question", source)
        self.assertIn("Required case questions", source)

    def test_final_report_prompt_does_not_request_second_confirmation(self):
        source = (SRC_ROOT / "tools" / "final_report.py").read_text(encoding="utf-8")
        self.assertIn("Generate the final report immediately", source)
        self.assertIn("Copy the supplied conclusion verbatim", source)
        self.assertNotIn("confirmed that they are ready to stop gathering new information", source)

    def test_prose_only_report_is_incomplete_not_valid_benchmark_output(self):
        parsed = _report_output(self.case, "A prose-only report with no payload.")
        self.assertFalse(parsed["structured_output_complete"])
        self.assertEqual(set(parsed["missing_structured_sections"]), {"findings", "claims", "reasoning_steps", "contradictions"})

    def test_reasoning_and_contradiction_scores_require_grounding(self):
        expected = self.case.data["ground_truth"]
        output = {
            "reasoning_steps": [1, 2, 3, 4, 5, 6],
            "reasoning_step_details": [{"id": i, "conclusion": "placeholder", "premise_entities": [], "premise_relations": []} for i in range(1, 7)],
            "contradictions": [{"contradiction_id": expected["contradictions"][0]["contradiction_id"], "description": "placeholder", "source_references": []}],
            "structured_output_valid": True,
        }
        scores = score_case(self.case.data, output)
        self.assertEqual(scores["reasoning_coverage"]["f1"], 1.0)
        self.assertLess(scores["reasoning_quality"]["semantic_similarity"], 1.0)
        self.assertEqual(scores["reasoning_quality"]["method"], "premise_ids_plus_token_entailment_proxy")
        self.assertEqual(scores["report_quality"]["checks"]["findings_match"], False)
        self.assertEqual(scores["report_quality"]["checks"]["contradictions_complete"], False)
        self.assertLess(scores["contradictions"]["f1"], 1.0)
        self.assertEqual(scores["contradictions"]["grounded_recall"], 0.0)

    def test_nested_json_report_payload_is_parsed_without_truncation(self):
        import json
        payload = {
            "findings": [{"question": "q", "answer": "a", "supporting_entities": ["ENT-001"], "source_references": ["SRC-001"]}],
            "claims": [], "reasoning_steps": [], "contradictions": []
        }
        parsed = _report_output(self.case, "```json\n" + json.dumps(payload) + "\n```")
        self.assertTrue(parsed["structured_output_complete"])
        self.assertEqual(parsed["key_findings"][0]["supporting_entities"], ["ENT-001"])

    def test_unfenced_nested_json_report_payload_is_parsed(self):
        import json
        payload = {"findings": [{"question": "q", "answer": "nested {text}"}], "claims": [], "reasoning_steps": [], "contradictions": []}
        parsed = _report_output(self.case, "Narrative before payload: " + json.dumps(payload))
        self.assertTrue(parsed["structured_output_complete"])
        self.assertEqual(parsed["key_findings"][0]["answer"], "nested {text}")

    def test_json_report_alias_fields_and_step_labels_are_normalized(self):
        import json
        payload = {
            "findings": [{"question": "q", "answer": "a", "entities": [], "sources": []}],
            "claims": [{"claim": "c", "sources": []}],
            "reasoning_steps": [{"step": "STEP 1", "entities": [], "relations": [], "conclusion": "x"}],
            "contradictions": [{"id": self.case.data["ground_truth"]["contradictions"][0]["contradiction_id"], "sources": [], "description": "d"}],
        }
        parsed = _report_output(self.case, "```json\n" + json.dumps(payload) + "\n```")
        self.assertEqual(parsed["reasoning_steps"], [1])
        self.assertEqual(parsed["reasoning_step_details"][0]["premise_entities"], [])
        self.assertFalse(parsed["structured_output_valid"])
        self.assertTrue(any("missing required proof steps" in error for error in parsed["structured_output_errors"]))

    def test_missing_reasoning_steps_invalidates_structured_report(self):
        import json
        payload = {"findings": [], "claims": [], "reasoning_steps": [{"id": 1, "conclusion": "x", "premise_entities": [], "premise_relations": []}], "contradictions": []}
        parsed = _report_output(self.case, "```json\n" + json.dumps(payload) + "\n```")
        self.assertFalse(parsed["structured_output_valid"])
        self.assertTrue(any("missing required proof steps" in error for error in parsed["structured_output_errors"]))

    def test_noncanonical_reasoning_relation_invalidates_structured_report(self):
        import json
        payload = {"findings": [], "claims": [], "reasoning_steps": [{"id": i, "conclusion": "x", "premise_entities": [], "premise_relations": ["free form relation"]} for i in range(1, 7)], "contradictions": []}
        parsed = _report_output(self.case, "```json\n" + json.dumps(payload) + "\n```")
        self.assertFalse(parsed["structured_output_valid"])
        self.assertTrue(any("non-canonical relation" in error for error in parsed["structured_output_errors"]))

    def test_blind_validation_does_not_require_hidden_ids(self):
        import json
        payload = {
            "findings": [{"question": "q", "answer": "a", "supporting_entities": ["Trading Technologies"], "source_references": ["SRC-001"]}],
            "claims": [],
            "reasoning_steps": [{"id": 99, "conclusion": "x", "premise_entities": ["Trading Technologies"], "premise_relations": ["worked at"]}],
            "contradictions": [{"id": "candidate-1", "description": "conflict", "source_references": ["SRC-001"]}],
        }
        report = "```json\n" + json.dumps(payload) + "\n```"
        parsed = _report_output(self.case, report, validation_mode="blind")
        self.assertTrue(parsed["structured_output_valid"])
        self.assertEqual(parsed["structured_output_errors"], [])

    def test_blind_validation_preserves_unknown_sources_for_scoring(self):
        import json
        payload = {"findings": [], "claims": [{"claim": "x", "source_references": ["S1"]}],
                   "reasoning_steps": [], "contradictions": []}
        parsed = _report_output(self.case, "```json\n" + json.dumps(payload) + "\n```", validation_mode="blind")
        self.assertTrue(parsed["structured_output_valid"])
        self.assertEqual(parsed["structured_output_errors"], [])
        self.assertEqual(parsed["claims"][0]["source_references"], ["S1"])

    def test_adapter_accepts_case_declared_proof_relations(self):
        case = load_case("case_005")
        parsed = {
            "findings": [], "claims": [], "contradictions": [],
            "reasoning_steps": [1, 2],
            "reasoning_step_details": [
                {"id": 1, "premise_entities": ["ENT-001"], "premise_relations": [], "conclusion": "Identify the primary target and gather independent public sources."},
                {"id": 2, "premise_entities": ["ENT-001", "ENT-002", "ENT-003", "ENT-004"], "premise_relations": ["also_known_as", "co_founded", "co_founded"], "conclusion": "Link aliases, organizations, people, platforms, or infrastructure across sources."},
            ],
        }
        adapted = adapt_report_output(case, parsed)
        self.assertTrue(adapted["structured_output_valid"])
        self.assertEqual(adapted["structured_output_errors"], [])


    def test_invalid_reasoning_premises_are_reported(self):
        scores = score_case(self.case.data, {
            "reasoning_steps": [1],
            "reasoning_step_details": [{"id": 1, "conclusion": "x", "premise_entities": ["ENT-999"], "premise_relations": ["made_up_relation"]}],
            "structured_output_valid": True,
        })
        detail = scores["reasoning_quality"]["details"][0]
        self.assertEqual(detail["invalid_premise_entities"], ["ENT-999"])
        self.assertEqual(detail["invalid_premise_relations"], ["made_up_relation"])

    def test_invalid_reasoning_steps_are_not_credited(self):
        scores = score_case(self.case.data, {
            "reasoning_steps": [999], "structured_output_valid": False,
            "structured_output_errors": ["unknown proof step 999"],
        })
        self.assertEqual(scores["reasoning_coverage"]["f1"], 0.0)
        self.assertEqual(scores["reasoning_coverage"]["invalid"], [999])
        self.assertLess(scores["report_quality"]["score"], 1.0)

    def test_case_quality_does_not_require_human_review_flag(self):
        case = {"sources": [{"source_id": "SRC-1", "uri": "https://example.org/a", "raw_text": "verified passage"}],
                "ground_truth": {"entities": [{"id": "ENT-1", "source_references": ["SRC-1"], "evidence": [{"source_id": "SRC-1", "quote": "verified passage"}]}]}}
        errors = audit(case, strict=True)
        self.assertFalse(any("not human verified" in error for error in errors))

    def test_case_quality_rejects_quote_not_in_snapshot(self):
        case = {"sources": [{"source_id": "SRC-1", "uri": "https://example.org/a", "raw_text": "actual passage"}],
                "ground_truth": {"entities": [{"id": "ENT-1", "source_references": ["SRC-1"], "evidence": [{"source_id": "SRC-1", "quote": "invented passage"}]}]}}
        errors = audit(case, strict=True)
        self.assertTrue(any("not present" in error for error in errors))

    def test_string_metadata_fields_are_supported(self):
        from tools.knowledge_base import _load_kb_config

        config = _load_kb_config()
        person = next(item for item in config["entity_types"] if item["type"] == "person")
        self.assertIn("nationality", person["metadata_fields"])


if __name__ == "__main__":
    unittest.main()
