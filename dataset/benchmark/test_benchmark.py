import unittest
import sys
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from .loader import load_case
from .replay import SourceReplay
from .scoring import score_case


class BenchmarkFrameworkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.case = load_case("case_001")

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

    def test_string_metadata_fields_are_supported(self):
        from tools.knowledge_base import _load_kb_config

        config = _load_kb_config()
        person = next(item for item in config["entity_types"] if item["type"] == "person")
        self.assertIn("nationality", person["metadata_fields"])


if __name__ == "__main__":
    unittest.main()
