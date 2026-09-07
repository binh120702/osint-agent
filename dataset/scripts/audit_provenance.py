"""Audit benchmark cases for verifiable public-source provenance.

This is intentionally a gate, not a source generator. It never fills missing
text or metadata and never treats an LLM-written summary as evidence.

Usage:
    python dataset/scripts/audit_provenance.py
    python dataset/scripts/audit_provenance.py --case OSINT-001
    python dataset/scripts/audit_provenance.py --strict
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlparse

CASES = Path(__file__).resolve().parents[1] / "cases"
HEX64 = re.compile(r"^[0-9a-f]{64}$", re.I)
FORBIDDEN_URI_MARKERS = ("mock", "example.test", "localhost", "127.0.0.1")


def audit(path: Path) -> list[str]:
    errors: list[str] = []
    try:
        case = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"cannot parse JSON: {exc}"]

    if case.get("ground_truth", {}).get("ground_truth_summary", "").lower().find("simulat") >= 0:
        errors.append("ground_truth_summary describes simulated data")

    seen: set[str] = set()
    for source in case.get("sources", []):
        sid = source.get("source_id", "<missing-source-id>")
        if sid in seen:
            errors.append(f"{sid}: duplicate source_id")
        seen.add(sid)
        uri = source.get("uri", "")
        parsed = urlparse(uri)
        if parsed.scheme != "https" or not parsed.netloc:
            errors.append(f"{sid}: source URI must be an HTTPS public URL")
        if any(marker in uri.lower() for marker in FORBIDDEN_URI_MARKERS):
            errors.append(f"{sid}: source URI looks synthetic/local: {uri}")

        content = source.get("content") or {}
        raw = source.get("raw_text", "")
        if len(raw.strip()) < 120:
            errors.append(f"{sid}: raw_text is missing or too short")
        digest = content.get("retrieved_sha256")
        if not isinstance(digest, str) or not HEX64.fullmatch(digest):
            errors.append(f"{sid}: missing retrieved_sha256 for the fetched payload")
        status = content.get("snapshot_status")
        if status not in {"refreshed_from_fetch", "historical_snapshot_not_refreshed"}:
            errors.append(f"{sid}: snapshot_status must identify a fetched public snapshot")
        if not content.get("publisher"):
            errors.append(f"{sid}: missing publisher")
        if not content.get("publication_date"):
            errors.append(f"{sid}: missing publication_date")
        if not content.get("date_accessed") and not content.get("fetch_date"):
            errors.append(f"{sid}: missing access/fetch date")
        if content.get("provenance_verified") is not True:
            errors.append(f"{sid}: provenance_verified is not true (requires human review)")
        if not content.get("verification_notes"):
            errors.append(f"{sid}: missing verification_notes")
        if content.get("evidence_summary") and not content.get("evidence_summary_is_source_text", False):
            # Summaries are useful metadata, but must not be mistaken for evidence.
            pass

    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", action="append", help="case id or filename; repeatable")
    parser.add_argument("--strict", action="store_true", help="return non-zero when any case fails")
    args = parser.parse_args()
    selected = set(args.case or [])
    paths = sorted(CASES.glob("*.json"))
    if selected:
        paths = [p for p in paths if p.stem in selected or json.loads(p.read_text(encoding="utf-8")).get("case_id") in selected]
    failed = 0
    for path in paths:
        issues = audit(path)
        if issues:
            failed += 1
            print(f"{path.name}: FAIL")
            for issue in issues:
                print(f"  - {issue}")
        else:
            print(f"{path.name}: PASS")
    print(f"audited={len(paths)} failed={failed}")
    return 1 if args.strict and failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
