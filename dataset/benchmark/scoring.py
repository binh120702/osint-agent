"""Deterministic and pluggable semantic scoring for benchmark outputs."""

from __future__ import annotations

import re
from collections import Counter
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
    value_key = normalize(entity.get("value"))
    # Production intentionally has richer tags (malware, software, file, keyword)
    # than this case's Alias label. Compare by value only when the case has one
    # unambiguous expected entity for that value.
    return expected_by_value.get(value_key, _entity_key(entity))


def _entity_scores(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected = {_entity_key(item) for item in case["ground_truth"]["entities"]}
    by_value = {}
    for item in case["ground_truth"]["entities"]:
        key = normalize(item["value"])
        canonical = _entity_key(item)
        if key in by_value and by_value[key] != canonical:
            by_value.pop(key, None)
        else:
            by_value[key] = canonical
    predicted = {_canonical_entity_key(item, by_value) for item in output.get("entities", []) if isinstance(item, dict)}
    result = _f1(predicted, expected)
    result["missing"] = sorted(expected - predicted)
    result["unexpected"] = sorted(predicted - expected)
    return result


def _relation_key(relation: dict[str, Any], entity_ids: dict[str, tuple[str, str]]) -> tuple[Any, ...] | None:
    if "source" in relation and "target" in relation:
        source = entity_ids.get(str(relation["source"]))
        target = entity_ids.get(str(relation["target"]))
    else:
        source = (normalize(relation.get("from_type")), normalize(relation.get("from_value")))
        target = (normalize(relation.get("to_type")), normalize(relation.get("to_value")))
    if not source or not target:
        return None
    return source, normalize(relation.get("relationship_type", relation.get("relation_type"))) , target


def _relation_scores(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    by_id = {item["id"]: _entity_key(item) for item in case["ground_truth"]["entities"]}
    by_value = {normalize(item["value"]): _entity_key(item) for item in case["ground_truth"]["entities"]}
    expected = {_relation_key(item, by_id) for item in case["ground_truth"]["relations"]}
    predicted = set()
    for item in output.get("relations", []):
        if not isinstance(item, dict):
            continue
        adapted = dict(item)
        adapted["from_type"], adapted["to_type"] = (
            by_value.get(normalize(adapted.get("from_value")), (adapted.get("from_type", ""),))[0],
            by_value.get(normalize(adapted.get("to_value")), (adapted.get("to_type", ""),))[0],
        )
        predicted.add(_relation_key(adapted, by_id))
    expected.discard(None)
    predicted.discard(None)
    result = _f1(predicted, expected)
    result["missing"] = sorted(expected - predicted, key=str)
    result["unexpected"] = sorted(predicted - expected, key=str)
    return result


def _source_ids(output: dict[str, Any], source_lookup: dict[str, str]) -> set[str]:
    values = set(str(value) for value in output.get("source_references", []) if value)
    for value in output.get("citations", []):
        candidate = str(value)
        values.add(source_lookup.get(normalize_uri(candidate), candidate))
    return values


def _contradiction_scores(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected = {str(item["contradiction_id"]) for item in case["ground_truth"].get("contradictions", [])}
    predicted = {str(item.get("contradiction_id", item.get("id", ""))) for item in output.get("contradictions", []) if isinstance(item, dict)}
    result = _f1(predicted, expected)
    result["missing"] = sorted(expected - predicted)
    result["unexpected"] = sorted(predicted - expected)
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
        supported = set(candidate.get("supporting_entities", [])) >= set(expected.get("supporting_entities", []))
        score = 1.0 if semantic >= 0.7 and supported else 0.5 if semantic >= 0.7 else 0.0
        scores.append(score)
        details.append({"question": expected["question"], "score": score, "semantic": semantic, "supporting_entities_complete": supported})
    return {"score": sum(scores) / len(scores) if scores else 0.0, "details": details}


def score_case(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None = None) -> dict[str, Any]:
    source_lookup = {normalize_uri(item["uri"]): item["source_id"] for item in case.get("sources", [])}
    expected_sources = set(source_lookup.values())
    cited_sources = _source_ids(output, source_lookup)
    traceability = {
        "correct_sources": sorted(cited_sources & expected_sources),
        "unknown_sources": sorted(cited_sources - expected_sources),
        "ratio": len(cited_sources & expected_sources) / len(cited_sources) if cited_sources else 0.0,
    }
    proof = case["ground_truth"].get("reasoning_proof_chains", [])
    covered_steps = set(output.get("reasoning_steps", []))
    reasoning = {"covered": sorted(covered_steps & {step["step_index"] for step in proof}), "total": len(proof),
                 "ratio": len(covered_steps & {step["step_index"] for step in proof}) / len(proof) if proof else 0.0}
    return {
        "entities": _entity_scores(case, output),
        "relations": _relation_scores(case, output),
        "contradictions": _contradiction_scores(case, output),
        "key_findings": _finding_scores(case, output, judge),
        "source_traceability": traceability,
        "reasoning_coverage": reasoning,
        "report_quality": output.get("report_quality"),
        "operational": output.get("operational", {}),
    }
