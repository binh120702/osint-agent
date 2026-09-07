"""Deterministic, auditable scoring for benchmark outputs."""

from __future__ import annotations

import re
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit


def normalize(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().casefold())


def normalize_uri(value: Any) -> str:
    parsed = urlsplit(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return normalize(value)
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), parsed.query, ""))


def _f1(predicted: set[Any], expected: set[Any]) -> dict[str, Any]:
    tp = len(predicted & expected)
    fp = len(predicted - expected)
    fn = len(expected - predicted)
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {"true_positive": tp, "false_positive": fp, "false_negative": fn,
            "precision": precision, "recall": recall,
            "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0.0}


def _entity_key(entity: dict[str, Any]) -> tuple[str, str]:
    return normalize(entity.get("type")), normalize(entity.get("value"))


def _canonical_entity_key(entity: dict[str, Any], expected_by_value: dict[str, tuple[str, str]]) -> tuple[str, str]:
    return expected_by_value.get(normalize(entity.get("value")), _entity_key(entity))


def _entity_scores(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected = {_entity_key(item) for item in case["ground_truth"]["entities"]}
    by_value: dict[str, tuple[str, str]] = {}
    for item in case["ground_truth"]["entities"]:
        value = normalize(item["value"])
        canonical = _entity_key(item)
        if value in by_value and by_value[value] != canonical:
            by_value.pop(value, None)
        else:
            by_value[value] = canonical
    predicted = {_canonical_entity_key(item, by_value) for item in output.get("entities", []) if isinstance(item, dict)}
    result = _f1(predicted, expected)
    result["missing"] = sorted(expected - predicted)
    result["unexpected"] = sorted(predicted - expected)
    return result


# Case authors may provide a relation_semantics mapping. These conservative
# aliases cover common production labels without asking an LLM to judge edges.
_RELATION_ALIASES = {
    "also_known_as": "alias_of", "alias_of": "alias_of",
    "co_founded": "founded", "founded": "founded",
    "based_in": "located_in", "located_in": "located_in",
    "performed_special_audit": "audited", "audited": "audited",
    "former_coo_of": "executive_of", "executive_of": "executive_of",
    "provided_software": "provided", "distributed_as_installer": "distributed",
    "contained_malware": "contained", "trojanized": "compromised",
    "associated_with": "associated_with", "linked_to": "associated_with",
    "uses_or_is_associated_with": "associated_with",
}


def _relation_semantics(case: dict[str, Any]) -> dict[str, str]:
    mapping = dict(_RELATION_ALIASES)
    for item in case.get("relation_semantics", []):
        if isinstance(item, dict) and item.get("canonical"):
            for alias in item.get("aliases", []) + [item["canonical"]]:
                mapping[normalize(alias)] = normalize(item["canonical"])
    return mapping


def _relation_key(relation: dict[str, Any], entity_ids: dict[str, tuple[str, str]], semantics: dict[str, str]) -> tuple[Any, ...] | None:
    if "source" in relation and "target" in relation:
        source = entity_ids.get(str(relation["source"]))
        target = entity_ids.get(str(relation["target"]))
    else:
        source = (normalize(relation.get("from_type")), normalize(relation.get("from_value")))
        target = (normalize(relation.get("to_type")), normalize(relation.get("to_value")))
    if not source or not target:
        return None
    relation_type = normalize(relation.get("relationship_type", relation.get("relation_type")))
    return source, semantics.get(relation_type, relation_type), target


def _relation_scores(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    by_id = {item["id"]: _entity_key(item) for item in case["ground_truth"]["entities"]}
    by_value = {normalize(item["value"]): _entity_key(item) for item in case["ground_truth"]["entities"]}
    semantics = _relation_semantics(case)
    expected = {_relation_key(item, by_id, semantics) for item in case["ground_truth"]["relations"]}
    predicted = set()
    for item in output.get("relations", []):
        if not isinstance(item, dict):
            continue
        adapted = dict(item)
        adapted["from_type"] = by_value.get(normalize(adapted.get("from_value")), (adapted.get("from_type", ""),))[0]
        adapted["to_type"] = by_value.get(normalize(adapted.get("to_value")), (adapted.get("to_type", ""),))[0]
        key = _relation_key(adapted, by_id, semantics)
        if key:
            predicted.add(key)
    expected.discard(None)
    result = _f1(predicted, expected)
    result["missing"] = sorted(expected - predicted, key=str)
    result["unexpected"] = sorted(predicted - expected, key=str)
    result["semantic_mapping"] = semantics
    return result


def _source_ids(output: dict[str, Any], source_lookup: dict[str, str]) -> set[str]:
    values = {str(value) for value in output.get("source_references", []) if value}
    for value in output.get("citations", []):
        candidate = str(value)
        values.add(source_lookup.get(normalize_uri(candidate), candidate))
    return values


def _contradiction_scores(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected_by_id = {str(item["contradiction_id"]): set(item.get("source_references", [])) for item in case["ground_truth"].get("contradictions", [])}
    predicted = {str(item.get("contradiction_id", item.get("id", ""))): set(item.get("source_references", [])) for item in output.get("contradictions", []) if isinstance(item, dict)}
    result = _f1(set(predicted), set(expected_by_id))
    result["details"] = [{"contradiction_id": cid,
                           "source_references_correct": predicted.get(cid, set()) >= refs,
                           "source_reference_recall": len(predicted.get(cid, set()) & refs) / len(refs) if refs else 1.0}
                          for cid, refs in expected_by_id.items() if cid in predicted]
    result["missing"] = sorted(set(expected_by_id) - set(predicted))
    result["unexpected"] = sorted(set(predicted) - set(expected_by_id))
    return result


def _overlap_score(answer: str, expected: str) -> float:
    left = set(re.findall(r"[a-z0-9_@.-]+", normalize(answer)))
    right = set(re.findall(r"[a-z0-9_@.-]+", normalize(expected)))
    return len(left & right) / len(right) if right else 0.0


def _finding_scores(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None) -> dict[str, Any]:
    findings = output.get("key_findings", [])
    scores = []
    details = []
    for expected in case["ground_truth"]["key_findings"]:
        candidate = next((item for item in findings if normalize(item.get("question")) == normalize(expected["question"])), None)
        if not candidate:
            scores.append(0.0)
            details.append({"question": expected["question"], "score": 0.0, "status": "missing"})
            continue
        semantic = judge(candidate.get("answer", ""), expected["answer"]) if judge else _overlap_score(candidate.get("answer", ""), expected["answer"])
        expected_entities = set(expected.get("supporting_entities", []))
        cited_entities = set(candidate.get("supporting_entities", []))
        cited_sources = set(candidate.get("source_references", []))
        supported = cited_entities >= expected_entities
        source_backed = bool(cited_sources)
        score = 1.0 if semantic >= 0.7 and supported and source_backed else 0.5 if semantic >= 0.7 else 0.0
        scores.append(score)
        details.append({"question": expected["question"], "score": score, "semantic": semantic,
                        "supporting_entities_complete": supported, "has_source_references": source_backed})
    return {"score": sum(scores) / len(scores) if scores else 0.0, "details": details}


def _claim_traceability(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected_sources = {s["source_id"] for s in case.get("sources", [])}
    claims = output.get("claims", [])
    if not claims:
        return {"claims": 0, "traceable_claims": 0, "ratio": 0.0, "status": "no_structured_claims"}
    traceable = [claim for claim in claims if set(claim.get("source_references", [])) & expected_sources]
    unknown = sorted({sid for claim in claims for sid in claim.get("source_references", []) if sid not in expected_sources})
    return {"claims": len(claims), "traceable_claims": len(traceable), "ratio": len(traceable) / len(claims), "unknown_sources": unknown}


def _report_quality(report: str, output: dict[str, Any]) -> dict[str, Any]:
    text = str(report or "")
    checks = {
        "non_empty": bool(text.strip()),
        "structured_findings": bool(output.get("key_findings")),
        "citations": bool(output.get("claims") and any(c.get("source_references") for c in output["claims"])),
        "uncertainty_language": bool(re.search(r"\b(alleged|reported|assessment|uncertain|unknown|evidence)\b", text, re.I)),
        "readable_length": 200 <= len(text) <= 30000,
    }
    return {"score": sum(checks.values()) / len(checks), "checks": checks, "scale": "deterministic rubric 0-1"}


def score_case(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None = None) -> dict[str, Any]:
    source_lookup = {normalize_uri(item["uri"]): item["source_id"] for item in case.get("sources", [])}
    expected_sources = set(source_lookup.values())
    cited_sources = _source_ids(output, source_lookup)
    proof_ids = {step["step_index"] for step in case["ground_truth"].get("reasoning_proof_chains", [])}
    covered_steps = {int(step) for step in output.get("reasoning_steps", []) if str(step).isdigit()}
    return {
        "output_validation": {"valid": output.get("structured_output_valid", False), "errors": output.get("structured_output_errors", [])},
        "entities": _entity_scores(case, output),
        "relations": _relation_scores(case, output),
        "contradictions": _contradiction_scores(case, output),
        "key_findings": _finding_scores(case, output, judge),
        "source_traceability": {
            "correct_sources": sorted(cited_sources & expected_sources),
            "unknown_sources": sorted(cited_sources - expected_sources),
            "ratio": len(cited_sources & expected_sources) / len(cited_sources) if cited_sources else 0.0,
            "claim_level": _claim_traceability(case, output),
        },
        "reasoning_coverage": {"covered": sorted(covered_steps & proof_ids), "total": len(proof_ids),
                                "ratio": len(covered_steps & proof_ids) / len(proof_ids) if proof_ids else 0.0,
                                "status": "structured_step_ids" if output.get("reasoning_steps") else "no_structured_steps"},
        "report_quality": _report_quality(output.get("report", ""), output),
        "operational": output.get("operational", {}),
    }
