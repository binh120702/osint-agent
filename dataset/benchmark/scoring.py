"""Deterministic, auditable scoring for benchmark outputs."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[2] / ".env"
    load_dotenv(_env_path)
    from dotenv import dotenv_values
    for _key, _value in dotenv_values(_env_path).items():
        if _value is not None:
            os.environ.setdefault(_key, _value)
except ImportError:
    pass


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


def _token_similarity(left: str, right: str) -> float:
    """Deterministic lexical entailment proxy; reports its method explicitly."""
    left_tokens = set(re.findall(r"[a-z0-9_]+", normalize(left)))
    right_tokens = set(re.findall(r"[a-z0-9_]+", normalize(right)))
    if not right_tokens:
        return 1.0 if not left_tokens else 0.0
    return len(left_tokens & right_tokens) / len(right_tokens)


_EMBEDDING_CACHE: dict[str, list[float]] = {}
_EMBEDDING_MODEL = os.getenv("BENCHMARK_EMBEDDING_MODEL", "text-embedding-3-small")
_BLIND_SEMANTIC_MODE = os.getenv("BLIND_SEMANTIC_MODE", "embedding").strip().lower()
_BLIND_STEP_ALIGNMENT_THRESHOLD = float(os.getenv("BLIND_STEP_ALIGNMENT_THRESHOLD", "0.35"))

def _embedding_vectors(texts: list[str]) -> list[list[float]]:
    """Fetch deterministic evaluator embeddings using the configured OpenAI-compatible API."""
    unique = list(dict.fromkeys(str(text) for text in texts))
    missing = [text for text in unique if text not in _EMBEDDING_CACHE]
    if missing:
        from openai import OpenAI
        client = OpenAI(api_key=os.environ["OPENAI_API_KEY"],
                        base_url=os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1"),
                        timeout=180, max_retries=2)
        response = client.embeddings.create(model=_EMBEDDING_MODEL, input=missing)
        for text, item in zip(missing, sorted(response.data, key=lambda value: value.index)):
            _EMBEDDING_CACHE[text] = list(item.embedding)
    return [_EMBEDDING_CACHE[text] for text in texts]

def _cosine(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    denominator = math.sqrt(sum(a * a for a in left)) * math.sqrt(sum(b * b for b in right))
    return max(0.0, min(1.0, numerator / denominator)) if denominator else 0.0

def _semantic_similarity_matrix(left: list[str], right: list[str]) -> list[list[float]]:
    vectors = _embedding_vectors(left + right)
    split = len(left)
    return [[_cosine(vectors[i], vectors[split + j]) for j in range(len(right))] for i in range(split)]

def _token_f1(left: str, right: str):
    left_tokens = set(re.findall(r"[a-z0-9_]+", normalize(left)))
    right_tokens = set(re.findall(r"[a-z0-9_]+", normalize(right)))
    if not left_tokens or not right_tokens:
        return 1.0 if not left_tokens and not right_tokens else 0.0
    overlap = len(left_tokens & right_tokens)
    precision, recall = overlap / len(left_tokens), overlap / len(right_tokens)
    return 2 * precision * recall / (precision + recall) if precision + recall else 0.0

def _blind_entity_aliases(case: dict[str, Any]) -> dict[str, str]:
    aliases = {}
    for item in case["ground_truth"].get("entities", []):
        for value in (item["id"], item.get("value", ""), f"{item.get('type', '')}:{item.get('value', '')}"):
            if str(value).strip(): aliases[normalize(value)] = str(item["id"])
    return aliases

def _blind_match_entities(values: Any, aliases: dict[str, str]) -> set[str]:
    matched = set()
    for value in values if isinstance(values, list) else []:
        text = normalize(value)
        if text in aliases:
            matched.add(aliases[text]); continue
        candidates = [(len(alias), entity_id) for alias, entity_id in aliases.items()
                      if len(alias) >= 4 and (alias in text or text in alias)]
        if candidates: matched.add(max(candidates)[1]
)
    return matched

def _blind_relation_recall(actual: Any, expected: Any) -> float:
    actual = [str(x) for x in actual if str(x).strip()] if isinstance(actual, list) else []
    expected = [str(x) for x in expected if str(x).strip()] if isinstance(expected, list) else []
    if not expected: return 1.0
    if _BLIND_SEMANTIC_MODE == "token":
        matrix = [[_token_f1(left, right) for right in expected] for left in actual] if actual else []
    else:
        matrix = _semantic_similarity_matrix(actual, expected) if actual else []
    scores = sorted(((matrix[i][j], i, j) for i in range(len(actual)) for j in range(len(expected))), reverse=True)
    used_a, used_e, total = set(), set(), 0.0
    for score, i, j in scores:
        if i not in used_a and j not in used_e and score >= 0.25:
            used_a.add(i); used_e.add(j); total += score
    return total / len(expected)

def _reasoning_quality(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None = None, blind: bool = False) -> dict[str, Any]:
    expected_items = {int(item["step_index"]): item for item in case["ground_truth"].get("reasoning_proof_chains", [])}
    valid_entity_ids = {str(item["id"]) for item in case["ground_truth"].get("entities", [])}
    valid_relation_types = {normalize(item["relationship_type"]) for item in case["ground_truth"].get("relations", [])}
    valid_relation_types.update(
        normalize(relation)
        for proof in case["ground_truth"].get("reasoning_proof_chains", [])
        for relation in proof.get("premise_relations", [])
    )
    details = {int(item["id"]): item for item in output.get("reasoning_step_details", [])
               if isinstance(item, dict) and str(item.get("id", "")).isdigit()}
    detail_rows = []
    if blind:
        actual_items = [item for item in output.get("reasoning_step_details", []) if isinstance(item, dict)]
        candidate_conclusions = [actual.get("conclusion", "") for actual in actual_items]
        expected_conclusions = [expected.get("conclusion", "") for expected in expected_items.values()]
        if _BLIND_SEMANTIC_MODE == "token":
            matrix = [[_token_f1(left, right) for right in expected_conclusions] for left in candidate_conclusions]
        else:
            matrix = _semantic_similarity_matrix(candidate_conclusions, expected_conclusions) if candidate_conclusions else []
        expected_ids = list(expected_items)
        candidates = sorted(((matrix[aid][ej], aid, expected_ids[ej])
                            for aid in range(len(actual_items))
                            for ej in range(len(expected_ids))), reverse=True)
        used_a, used_e, matches = set(), set(), {}
        for similarity, aid, eid in candidates:
            if aid not in used_a and eid not in used_e and similarity >= _BLIND_STEP_ALIGNMENT_THRESHOLD:
                used_a.add(aid); used_e.add(eid); matches[eid] = actual_items[aid]
        aliases = _blind_entity_aliases(case)
    else:
        matches = {step_id: details.get(step_id) for step_id in expected_items if details.get(step_id)}
        aliases = {}
    for step_id, expected in expected_items.items():
        actual = matches.get(step_id) if blind else details.get(step_id)
        if not actual:
            continue
        expected_entities = set(expected.get("premise_entities", []))
        expected_relations = set(expected.get("premise_relations", []))
        raw_entities = actual.get("premise_entities", [])
        actual_entities = _blind_match_entities(raw_entities, aliases) if blind else {str(value) for value in raw_entities}
        actual_relations = [str(value) for value in actual.get("premise_relations", [])]
        expected_relations = {normalize(value) for value in expected_relations}
        invalid_entities = sorted(actual_entities - set(
            item["id"] for item in case["ground_truth"].get("entities", [])
        ))
        invalid_relations = [] if blind else sorted({normalize(x) for x in actual_relations} - valid_relation_types)
        entity_recall = len(actual_entities & expected_entities) / len(expected_entities) if expected_entities else 1.0
        relation_recall = _blind_relation_recall(actual_relations, list(expected_relations)) if blind else len(set(actual_relations) & expected_relations) / len(expected_relations) if expected_relations else 1.0
        premise_score = (0.70 * entity_recall + 0.30 * relation_recall) if blind else (entity_recall + relation_recall) / 2
        conclusion_score = judge(actual.get("conclusion", ""), expected.get("conclusion", "")) if judge else (_token_f1(actual.get("conclusion", ""), expected.get("conclusion", "")) if _BLIND_SEMANTIC_MODE == "token" else _cosine(*_embedding_vectors([actual.get("conclusion", ""), expected.get("conclusion", "")])) if blind else _token_similarity(actual.get("conclusion", ""), expected.get("conclusion", "")))
        grounded_score = (0.50 * premise_score + 0.50 * conclusion_score) if blind else premise_score * conclusion_score
        detail_rows.append({"id": step_id, "premise_score": premise_score, "entity_recall": entity_recall,
                            "relation_recall": relation_recall, "conclusion_similarity": conclusion_score,
                            "invalid_premise_entities": invalid_entities, "invalid_premise_relations": invalid_relations,
                            "grounded_score": grounded_score})
    coverage = len(matches) / len(expected_items) if blind else len(details.keys() & expected_items.keys()) / len(expected_items) if expected_items else 1.0
    grounded = sum(row["grounded_score"] for row in detail_rows) / len(detail_rows) if detail_rows else 0.0
    coverage_factor = (0.5 + 0.5 * coverage) if blind else coverage
    return {"covered": len(detail_rows), "expected": len(expected_items), "coverage": coverage,
            "semantic_similarity": sum(row["conclusion_similarity"] for row in detail_rows) / len(detail_rows) if detail_rows else 0.0,
            "premise_grounding": sum(row["premise_score"] for row in detail_rows) / len(detail_rows) if detail_rows else 0.0,
            "grounded_score": coverage_factor * grounded, "method": f"blind_{_BLIND_SEMANTIC_MODE}_relaxed_step_alignment_v4_threshold_{_BLIND_STEP_ALIGNMENT_THRESHOLD:g}" if blind else "premise_ids_plus_token_entailment_proxy",
            "formula": f"semantic_mode={_BLIND_SEMANTIC_MODE}; alignment_threshold={_BLIND_STEP_ALIGNMENT_THRESHOLD:g}; coverage_factor=(0.5+0.5*coverage); premise=0.7*entity+0.3*relation; step=0.5*premise+0.5*conclusion" if blind else "premise*conclusion",
            "details": detail_rows}


def _report_quality(report: str, output: dict[str, Any], finding_score: dict[str, Any], traceability: dict[str, Any], contradiction_score: dict[str, Any], reasoning_score: dict[str, Any]) -> dict[str, Any]:
    text = str(report or "")
    checks = {
        "non_empty": bool(text.strip()),
        "structured_output_complete": bool(output.get("structured_output_complete", False)),
        "structured_output_valid": bool(output.get("structured_output_valid", False)),
        "findings_present": bool(output.get("key_findings")),
        "findings_match": finding_score.get("recall", 0.0) >= 1.0 and finding_score.get("precision", 0.0) >= 1.0,
        "claims_traceable": traceability.get("ratio", 0.0) >= 0.5,
        "contradictions_complete": contradiction_score.get("recall", 0.0) >= 1.0,
        "contradictions_grounded": contradiction_score.get("grounded_recall", 0.0) >= 1.0,
        "finding_sources_grounded": traceability.get("finding_level", {}).get("ratio", 0.0) >= 1.0,
        "reasoning_conclusions_grounded": reasoning_score.get("grounded_score", 0.0) >= 0.5,
        "uncertainty_language": bool(re.search(r"\b(alleged|reported|assessment|uncertain|unknown|evidence)\b", text, re.I)),
        "readable_length": 200 <= len(text) <= 30000,
    }
    return {"score": sum(checks.values()) / len(checks), "checks": checks, "scale": "deterministic rubric 0-1"}


def score_case(case: dict[str, Any], output: dict[str, Any], judge: Callable[[str, str], float] | None = None, blind: bool = False) -> dict[str, Any]:
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
    reasoning_quality = _reasoning_quality(case, output, judge, blind=blind)
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
