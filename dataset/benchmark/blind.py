"""Build candidate-facing benchmark inputs without ground-truth leakage."""
from __future__ import annotations

from copy import deepcopy
from typing import Any

# Benchmark annotations that are useful to the scorer but must never reach a
# candidate in blind mode.  Source evidence, URIs, hashes, and normal source
# metadata remain available as immutable snapshots.
_ANNOTATION_KEYS = {
    "ground_truth", "evaluation_notes", "supports_findings", "expected_findings",
    "expected_answers", "expected_entities", "expected_sources", "reasoning_proof_chains",
    "contradictions", "required_questions", "required_findings", "canonical_entities",
    "canonical_entity_reference", "proof_conclusions", "allowed_relations",
}


def _strip_annotations(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_annotations(item)
            for key, item in value.items()
            if key not in _ANNOTATION_KEYS
        }
    if isinstance(value, list):
        return [_strip_annotations(item) for item in value]
    return value


def blind_case(data: dict[str, Any]) -> dict[str, Any]:
    """Return task and evidence snapshots without benchmark annotations."""
    result = {
        "case_id": data["case_id"],
        "investigation_goal": data["investigation_goal"],
        "target": data["target"],
        "sources": deepcopy(data.get("sources", [])),
        "evaluation_mode": "blind",
    }
    return _strip_annotations(result)


def blind_prompt(data: dict[str, Any]) -> str:
    """Prompt shared by candidates in the blind track."""
    return (
        "Investigate the following case using only evidence returned by the benchmark tools, "
        "then return a complete final report. Do not ask whether to continue.\n"
        f"Goal: {data['investigation_goal']}\nTarget: {data['target']}\n\n"
        "Do not invent facts. Label allegations, assessments, and uncertainty. Cite only source IDs "
        "returned by tools. Include readable Markdown and a fenced JSON object containing arrays "
        "named findings, claims, reasoning_steps, and contradictions. Each finding should contain "
        "question, answer, supporting_entities, and source_references; each claim should contain "
        "claim and source_references; each reasoning step should contain id, conclusion, "
        "premise_entities, and premise_relations; each contradiction should contain "
        "contradiction_id, description, and source_references. Use IDs and relationship names only "
        "when they are supported by tool-returned evidence. Report uncertainty or omit unsupported "
        "items. The evaluator will score the report against the private benchmark annotations."
    )
