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
    expected_items = case["ground_truth"].get("contradictions", [])
    expected_by_id = {str(item["contradiction_id"]): set(item.get("source_references", [])) for item in expected_items}
    predicted_items = [item for item in output.get("contradictions", []) if isinstance(item, dict)]
    predicted = {str(item.get("contradiction_id", item.get("id", ""))): set(item.get("source_references", [])) for item in predicted_items}
    result = _f1(set(predicted), set(expected_by_id))
    details = []
    for cid, refs in expected_by_id.items():
        cited = predicted.get(cid, set())
        details.append({"contradiction_id": cid,
                        "source_references_correct": cited >= refs,
                        "source_reference_recall": len(cited & refs) / len(refs) if refs else 1.0})
    result["details"] = [item for item in details if item["contradiction_id"] in predicted]
    result["missing"] = sorted(set(expected_by_id) - set(predicted))
    result["unexpected"] = sorted(set(predicted) - set(expected_by_id))
    recalls = [item["source_reference_recall"] for item in details if item["contradiction_id"] in predicted]
    result["grounded_recall"] = sum(recalls) / len(recalls) if recalls else 0.0
    result["grounded_f1"] = result["f1"] * result["grounded_recall"]
    return result


def _overlap_score(answer: str, expected: str) -> float:
    left = set(re.findall(r"[a-z0-9_@.-]+", normalize(answer)))
    right = set(re.findall(r"[a-z0-9_@.-]+", normalize(expected)))
    return len(left & right) / len(right) if right else 0.0


def _finding_scores(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None) -> dict[str, Any]:
    """Match paraphrased findings one-to-one instead of requiring exact questions."""
    expected = case["ground_truth"].get("key_findings", [])
    predicted = [item for item in output.get("key_findings", []) if isinstance(item, dict)]
    pairs = []
    for pi, candidate in enumerate(predicted):
        question_similarity = _overlap_score(candidate.get("question", ""), " ".join(
            [expected_item["question"] for expected_item in expected])) if expected else 0.0
        answer_scores = [(judge(candidate.get("answer", ""), item.get("answer", "")) if judge else
                         _overlap_score(candidate.get("answer", ""), item.get("answer", "")), ei)
                        for ei, item in enumerate(expected)]
        if answer_scores:
            answer_similarity, ei = max(answer_scores)
            pairs.append((answer_similarity + 0.25 * question_similarity, pi, ei, answer_similarity))
    matched = {}
    for _, pi, ei, answer_similarity in sorted(pairs, reverse=True):
        if pi in matched or ei in {x[0] for x in matched.values()}:
            continue
        if answer_similarity >= 0.35:
            matched[pi] = (ei, answer_similarity)
    details = []
    for ei, item in enumerate(expected):
        match = next(((pi, sim) for pi, (found_ei, sim) in matched.items() if found_ei == ei), None)
        if not match:
            details.append({"question": item["question"], "status": "missing", "score": 0.0})
            continue
        candidate, semantic = predicted[match[0]], match[1]
        expected_entities = set(item.get("supporting_entities", []))
        cited_entities = set(candidate.get("supporting_entities", []))
        cited_sources = set(candidate.get("source_references", []))
        expected_sources = set(item.get("source_references", []))
        entity_ratio = len(cited_entities & expected_entities) / len(expected_entities) if expected_entities else 1.0
        source_ratio = len(cited_sources & expected_sources) / len(expected_sources) if expected_sources else (1.0 if cited_sources else 0.0)
        score = semantic * (0.4 + 0.3 * entity_ratio + 0.3 * source_ratio) if cited_sources else semantic * 0.4
        details.append({"question": item["question"], "status": "matched", "score": score,
                        "semantic": semantic, "supporting_entity_recall": entity_ratio,
                        "source_recall": source_ratio, "has_source_references": bool(cited_sources)})
    tp = len(matched)
    precision = tp / len(predicted) if predicted else 0.0
    recall = tp / len(expected) if expected else 1.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"score": sum(x["score"] for x in details) / len(details) if details else 0.0,
            "precision": precision, "recall": recall, "f1": f1,
            "predicted": len(predicted), "expected": len(expected), "matched": tp, "details": details}


def _claim_traceability(case: dict[str, Any], output: dict[str, Any]) -> dict[str, Any]:
    expected_sources = {s["source_id"] for s in case.get("sources", [])}
    available_sources = set(output.get("available_source_references", []))
    claims = [claim for claim in output.get("claims", []) if isinstance(claim, dict)]
    if not claims:
        return {"claims": 0, "traceable_claims": 0, "ratio": 0.0, "status": "no_structured_claims"}
    traceable = [claim for claim in claims if set(claim.get("source_references", [])) & available_sources & expected_sources]
    unknown = sorted({sid for claim in claims for sid in claim.get("source_references", []) if sid not in expected_sources})
    unavailable = sorted({sid for claim in claims for sid in claim.get("source_references", []) if sid in expected_sources and sid not in available_sources})
    return {"claims": len(claims), "traceable_claims": len(traceable), "ratio": len(traceable) / len(claims),
            "unknown_sources": unknown, "unavailable_sources": unavailable}


def _reasoning_quality(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None = None) -> dict[str, Any]:
    expected = {int(item["step_index"]): item.get("conclusion", "") for item in case["ground_truth"].get("reasoning_proof_chains", [])}
    details = {int(item["id"]): item.get("conclusion", "") for item in output.get("reasoning_step_details", []) if isinstance(item, dict) and str(item.get("id", "")).isdigit()}
    scores = []
    for step_id, conclusion in expected.items():
        if step_id not in details:
            continue
        scores.append(judge(details[step_id], conclusion) if judge else _overlap_score(details[step_id], conclusion))
    semantic = sum(scores) / len(scores) if scores else 0.0
    coverage = len(set(details) & set(expected)) / len(expected) if expected else 1.0
    return {"covered": len(scores), "expected": len(expected), "coverage": coverage, "semantic_similarity": semantic,
            "grounded_score": coverage * semantic}


def _report_quality(report: str, output: dict[str, Any], finding_score: dict[str, Any], traceability: dict[str, Any], contradiction_score: dict[str, Any], reasoning_score: dict[str, Any]) -> dict[str, Any]:
    text = str(report or "")
    checks = {
        "non_empty": bool(text.strip()),
        "structured_output_complete": bool(output.get("structured_output_complete", False)),
        "structured_output_valid": bool(output.get("structured_output_valid", False)),
        "findings_present": bool(output.get("key_findings")),
        "findings_match": finding_score.get("f1", 0.0) >= 0.5,
        "claims_traceable": traceability.get("ratio", 0.0) >= 0.5,
        "contradictions_grounded": contradiction_score.get("grounded_recall", 0.0) >= 0.5,
        "finding_sources_grounded": traceability.get("finding_level", {}).get("ratio", 0.0) >= 0.5,
        "reasoning_conclusions_grounded": reasoning_score.get("grounded_score", 0.0) >= 0.5,
        "uncertainty_language": bool(re.search(r"\b(alleged|reported|assessment|uncertain|unknown|evidence)\b", text, re.I)),
        "readable_length": 200 <= len(text) <= 30000,
    }
    return {"score": sum(checks.values()) / len(checks), "checks": checks, "scale": "deterministic rubric 0-1"}


def score_case(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None = None) -> dict[str, Any]:
    source_lookup = {normalize_uri(item["uri"]): item["source_id"] for item in case.get("sources", [])}
    expected_sources = set(source_lookup.values())
    cited_sources = _source_ids(output, source_lookup)
    available_sources = set(output.get("available_source_references", []))
    proof_ids = {step["step_index"] for step in case["ground_truth"].get("reasoning_proof_chains", [])}
    covered_steps = {int(step) for step in output.get("reasoning_steps", []) if str(step).isdigit()}
    valid_steps = covered_steps & proof_ids
    invalid_steps = covered_steps - proof_ids
    step_precision = len(valid_steps) / len(covered_steps) if covered_steps else 0.0
    step_recall = len(valid_steps) / len(proof_ids) if proof_ids else 1.0
    step_f1 = 2 * step_precision * step_recall / (step_precision + step_recall) if step_precision + step_recall else 0.0
    finding_scores = _finding_scores(case, output, judge)
    claim_traceability = _claim_traceability(case, output)
    contradiction_scores = _contradiction_scores(case, output)
    reasoning_quality = _reasoning_quality(case, output, judge)
    predicted_findings = [item for item in output.get("key_findings", []) if isinstance(item, dict)]
    available_expected = available_sources & expected_sources
    finding_sources = [set(item.get("source_references", [])) for item in predicted_findings]
    traceable_findings = sum(bool(refs & available_expected) for refs in finding_sources)
    traceability = {
        "correct_sources": sorted(cited_sources & expected_sources),
        "unknown_sources": sorted(cited_sources - expected_sources),
        "unavailable_sources": sorted(cited_sources & expected_sources - available_sources),
        "source_precision": len(cited_sources & expected_sources) / len(cited_sources) if cited_sources else 0.0,
        "source_recall": len(cited_sources & available_expected) / len(available_expected) if available_expected else 0.0,
        "ratio": claim_traceability["ratio"],
        "claim_level": claim_traceability,
        "finding_level": {"findings": len(predicted_findings), "traceable_findings": traceable_findings,
                          "ratio": traceable_findings / len(predicted_findings) if predicted_findings else 0.0},
    }
    return {
        "output_validation": {"valid": output.get("structured_output_valid", False), "errors": output.get("structured_output_errors", [])},
        "entities": _entity_scores(case, output),
        "relations": _relation_scores(case, output),
        "contradictions": contradiction_scores,
        "key_findings": finding_scores,
        "source_traceability": traceability,
        "reasoning_coverage": {"covered": sorted(valid_steps), "invalid": sorted(invalid_steps), "total": len(proof_ids),
                                "precision": step_precision, "recall": step_recall, "f1": step_f1,
                                "ratio": step_recall,
                                "status": "structured_step_ids" if output.get("reasoning_steps") else "no_structured_steps"},
        "report_quality": _report_quality(output.get("report", ""), output, finding_scores, traceability, contradiction_scores, reasoning_quality),
        "reasoning_quality": reasoning_quality,
        "operational": output.get("operational", {}),
    }
