"""Quality gate for benchmark cases.

This gate checks evidence and mechanical integrity. It deliberately does not
require a human-review flag; reviewers may record that metadata separately.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

CASES = Path(__file__).resolve().parent.parent / "cases"


def audit(case: dict, strict: bool = False) -> list[str]:
    errors: list[str] = []
    sources = {s.get("source_id"): s for s in case.get("sources", [])}
    entities = {e.get("id"): e for e in case.get("ground_truth", {}).get("entities", [])}
    for sid, source in sources.items():
        uri = source.get("uri", "")
        if urlparse(uri).scheme != "https":
            errors.append(f"{sid}: non-HTTPS source URI")
        if len(source.get("raw_text", "").strip()) < 120:
            errors.append(f"{sid}: insufficient raw_text")
    def check_evidence(owner: str, item: dict) -> None:
        evidence = item.get("evidence", [])
        if strict and not evidence:
            errors.append(f"{owner}: missing exact evidence passages")
        for passage in evidence:
            sid = passage.get("source_id")
            quote = passage.get("quote", "")
            if sid not in sources:
                errors.append(f"{owner}: evidence references unknown source {sid}")
            elif quote not in sources[sid].get("raw_text", ""):
                errors.append(f"{owner}: evidence quote is not present in {sid} snapshot")

    for entity in entities.values():
        check_evidence(entity["id"], entity)
        if not entity.get("source_references"):
            errors.append(f"{entity['id']}: no source references")
        for sid in entity.get("source_references", []):
            if sid not in sources:
                errors.append(f"{entity['id']}: unknown source {sid}")
    for index, relation in enumerate(case.get("ground_truth", {}).get("relations", [])):
        check_evidence(f"relation[{index}]", relation)
        if relation.get("source") not in entities or relation.get("target") not in entities:
            errors.append("relation references unknown entity")
        if not relation.get("source_references"):
            errors.append("relation has no source references")
    for index, contradiction in enumerate(case.get("ground_truth", {}).get("contradictions", [])):
        check_evidence(f"contradiction[{index}]", contradiction)
    for index, step in enumerate(case.get("ground_truth", {}).get("reasoning_proof_chains", [])):
        check_evidence(f"step[{index}]", step)
    for index, finding in enumerate(case.get("ground_truth", {}).get("key_findings", [])):
        check_evidence(f"finding[{index}]", finding)
        if not finding.get("supporting_entities"):
            errors.append(f"finding has no supporting entities: {finding.get('question', '')}")
        for eid in finding.get("supporting_entities", []):
            if eid not in entities:
                errors.append(f"finding references unknown entity {eid}")
    # Strong evidence annotations are intentionally opt-in until cases migrate.
    for claim in case.get("ground_truth", {}).get("evidence_claims", []):
        if not claim.get("source_id") or not claim.get("quote"):
            errors.append("evidence_claim requires source_id and quote")
        elif claim["source_id"] not in sources:
            errors.append(f"evidence_claim references unknown source {claim['source_id']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args()
    selected = set(args.case or [])
    paths = sorted(CASES.glob("*.json"))
    if selected:
        paths = [p for p in paths if p.stem in selected or json.loads(p.read_text(encoding="utf-8")).get("case_id") in selected]
    failed = 0
    for path in paths:
        case = json.loads(path.read_text(encoding="utf-8"))
        errors = audit(case, strict=args.strict)
        if errors:
            failed += 1
            print(f"{path.name}: FAIL")
            for error in errors:
                print(f"  - {error}")
        else:
            print(f"{path.name}: PASS")
    print(f"audited={len(paths)} failed={failed}")
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
