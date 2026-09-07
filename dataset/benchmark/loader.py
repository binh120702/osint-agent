"""Case loading and integrity validation for OSINT-Bench."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SCHEMA_PATH = ROOT / "schema" / "case_schema.json"
CASES_PATH = ROOT / "cases"


@dataclass(frozen=True)
class BenchmarkCase:
    path: Path
    data: dict[str, Any]
    sha256: str

    @property
    def case_id(self) -> str:
        return str(self.data["case_id"])


def _validate_schema(data: dict[str, Any]) -> None:
    try:
        from jsonschema import validate
    except ImportError as exc:  # pragma: no cover - dependency is part of dev setup
        raise RuntimeError("Install jsonschema to validate benchmark cases") from exc

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validate(instance=data, schema=schema)


def _validate_integrity(data: dict[str, Any]) -> None:
    sources = {item["source_id"] for item in data.get("sources", [])}
    entities = {item["id"] for item in data["ground_truth"].get("entities", [])}
    errors: list[str] = []

    for entity in data["ground_truth"].get("entities", []):
        errors.extend(
            f"entity {entity['id']} references unknown source {source}"
            for source in entity.get("source_references", [])
            if source not in sources
        )
    for relation in data["ground_truth"].get("relations", []):
        if relation["source"] not in entities:
            errors.append(f"relation references unknown entity {relation['source']}")
        if relation["target"] not in entities:
            errors.append(f"relation references unknown entity {relation['target']}")
        errors.extend(
            f"relation references unknown source {source}"
            for source in relation.get("source_references", [])
            if source not in sources
        )
    for contradiction in data["ground_truth"].get("contradictions", []):
        errors.extend(
            f"contradiction {contradiction['contradiction_id']} references unknown source {source}"
            for source in contradiction.get("source_references", [])
            if source not in sources
        )
    for step in data["ground_truth"].get("reasoning_proof_chains", []):
        errors.extend(
            f"proof step {step['step_index']} references unknown entity {entity}"
            for entity in step.get("premise_entities", [])
            if entity not in entities
        )
    for finding in data["ground_truth"].get("key_findings", []):
        errors.extend(
            f"finding references unknown entity {entity}"
            for entity in finding.get("supporting_entities", [])
            if entity not in entities
        )
    if errors:
        raise ValueError("; ".join(errors))


def load_case(case_id_or_path: str | Path, validate: bool = True) -> BenchmarkCase:
    requested = Path(case_id_or_path)
    path = requested if requested.exists() else CASES_PATH / f"{case_id_or_path}.json"
    if not path.exists():
        matches = sorted(CASES_PATH.glob(f"*{case_id_or_path}*.json"))
        if not matches:
            # Case IDs such as OSINT-001 are metadata identifiers and do not
            # necessarily occur in the filename. Resolve them without relying
            # on filename conventions.
            for candidate in sorted(CASES_PATH.glob("*.json")):
                try:
                    candidate_data = json.loads(candidate.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if str(candidate_data.get("case_id", "")) == str(case_id_or_path):
                    matches.append(candidate)
        if len(matches) != 1:
            raise FileNotFoundError(f"Could not resolve benchmark case: {case_id_or_path}")
        path = matches[0]

    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Benchmark case must be a JSON object: {path}")
    if validate:
        _validate_schema(data)
        _validate_integrity(data)
    return BenchmarkCase(path=path, data=data, sha256=hashlib.sha256(raw).hexdigest())


def load_cases(selector: str = "all", validate: bool = True) -> list[BenchmarkCase]:
    if selector.lower() != "all":
        return [load_case(selector, validate=validate)]
    return [load_case(path, validate=validate) for path in sorted(CASES_PATH.glob("*.json"))]
