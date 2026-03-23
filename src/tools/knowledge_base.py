import json
from pathlib import Path
from typing import Any, List, Dict

from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool

from llms.openai_client import OPENAI_CLIENT


def _kb_path() -> Path:
    """Return the path to the knowledge base text file."""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "kb_entities.txt"


def _kb_config_path() -> Path:
    """Path to knowledge base config for dynamic entity type tag sets."""
    root = Path(__file__).resolve().parent.parent  # src/
    return root / "config" / "knowledge_base_config.json"


def _load_kb_config() -> Dict[str, Any]:
    """
    Load KB configuration (entity types etc.) from JSON.

    Falls back to defaults if the file is missing or invalid.
    """
    default = {
        "entity_types": [
            {
                "type": "person",
                "description": "A real human person (name, full name, or variant spelling).",
            },
            {
                "type": "alias",
                "description": "An AKA / nickname / alternate spelling used by the same person (short label, not a full identity).",
            },
            {
                "type": "organization",
                "description": "A company, nonprofit, agency, or group (brand/legal name).",
            },
            {
                "type": "handle",
                "description": "A social screen name/username without a platform prefix (example: 'elonmusk' or '@elonmusk' without the @).",
            },
            {
                "type": "account",
                "description": "A full account identifier tied to a platform (example: 'twitter:elonmusk', 'github:octocat', or profile URL).",
            },
            {
                "type": "domain",
                "description": "A website domain or subdomain (example: 'example.com').",
            },
            {
                "type": "url",
                "description": "A full HTTP/HTTPS URL to a specific resource/page (include scheme).",
            },
            {
                "type": "repository",
                "description": "A GitHub/code repository identifier (example: 'owner/repo' or a repo URL).",
            },
            {
                "type": "email",
                "description": "An email address.",
            },
            {
                "type": "phone",
                "description": "A phone number (include country code if possible).",
            },
            {
                "type": "ip",
                "description": "An IP address (IPv4 or IPv6).",
            },
            {
                "type": "location",
                "description": "A geographic location (city, region, country, or approximate place).",
            },
            {
                "type": "date",
                "description": "A specific date or normalized date string (example: '2026-03-09' or '2024-05').",
            },
            {
                "type": "event",
                "description": "A named incident/event/milestone (example: '2024 data breach', 'arrest', 'conference 2023').",
            },
            {
                "type": "document",
                "description": "A document/artifact identifier (example: report title, PDF name, or 'case file' label).",
            },
            {
                "type": "keyword",
                "description": "A notable keyword/phrase that anchors investigation (example: campaign name, tag, tagline, or unique phrase).",
            },
            {
                "type": "other",
                "description": "Any entity that does not fit the categories above.",
            },
        ]
    }

    config_path = _kb_config_path()
    if not config_path.exists():
        return default

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return default

    entity_types = raw.get("entity_types", default["entity_types"])
    if not isinstance(entity_types, list):
        return default

    normalized_types: List[Dict[str, str]] = []
    seen: set[str] = set()

    for entry in entity_types:
        # Backwards compatible: allow ["person", "domain"] style.
        if isinstance(entry, str):
            t = entry.strip()
            if not t or t in seen:
                continue
            seen.add(t)
            normalized_types.append({"type": t, "description": ""})
            continue

        if not isinstance(entry, dict):
            continue

        t = str(entry.get("type", "") or "").strip()
        if not t or t in seen:
            continue

        desc = str(entry.get("description", "") or "").strip()
        seen.add(t)
        normalized_types.append({"type": t, "description": desc})

    if not normalized_types:
        return default

    # Fill missing descriptions from defaults where possible.
    defaults_by_type: Dict[str, str] = {
        item["type"]: item.get("description", "") for item in default["entity_types"]
    }
    for item in normalized_types:
        if not item.get("description") and item["type"] in defaults_by_type:
            item["description"] = defaults_by_type[item["type"]]

    # Return normalized structure.
    return {**default, "entity_types": normalized_types}


def _entities_system_prompt(entity_types: List[Dict[str, str]]) -> str:
    allowed = [t["type"] for t in entity_types if t.get("type")]
    allowed_str = " | ".join(allowed) if allowed else "other"

    type_meanings = "\n".join(
        [f"- {t['type']}: {t.get('description', '').strip()}" for t in entity_types if t.get("type")]
    ).strip()
    if not type_meanings:
        type_meanings = "- other: (unspecified)"

    return f"""
You extract a structured OSINT knowledge base from investigation notes.

Given free-form text about a target (person, organization, accounts, domains, etc.),
identify key entities and facts that should be stored for later reasoning and reporting.

Return a JSON object with this shape:
{{
  "entities": [
    {{
      "type": "{allowed_str}",
      "value": "short identifier (e.g. username, full name, domain)",
      "notes": "optional short note with key evidence or context"
    }},
    ...
  ]
}}

Entity type meanings:
{type_meanings}

Guidelines:
- Be concise but include all important entities and aliases.
- Prefer stable identifiers (usernames, profile URLs, domains) over long sentences.
- Use `notes` to briefly capture the most important evidence or context.
"""


def _read_kb_lines() -> List[str]:
    path = _kb_path()
    if not path.exists():
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_kb_lines(lines: List[str]) -> None:
    path = _kb_path()
    content = "\n".join(lines) + "\n" if lines else ""
    path.write_text(content, encoding="utf-8")


@tool
def kb_extract_entities(text: str) -> str:
    """Extract key entities from investigation text and append them to the OSINT knowledge base.

    Input:
        text: Any notes, tool outputs, or summaries related to the investigation.

    Behaviour:
        - Uses the LLM to extract structured entities (person, account, domain, etc.).
        - Appends them to a simple text knowledge base file (data/kb_entities.txt),
          merging and de-duplicating existing entries.
        - Returns the list of entities that are now stored in the knowledge base.
    """
    if not text or not text.strip():
        return "No text provided for entity extraction."

    kb_config = _load_kb_config()
    entity_types = kb_config.get("entity_types", [])
    if not isinstance(entity_types, list):
        entity_types = []
    # Ensure entries are objects (we support string-only configs too).
    normalized: List[Dict[str, str]] = []
    for entry in entity_types:
        if isinstance(entry, str):
            normalized.append({"type": entry, "description": ""})
        elif isinstance(entry, dict) and entry.get("type"):
            normalized.append(
                {"type": str(entry.get("type", "")).strip(), "description": str(entry.get("description", "")).strip()}
            )
    entity_types = normalized

    messages = [
        SystemMessage(content=_entities_system_prompt(entity_types)),
        HumanMessage(content=text),
    ]
    response = OPENAI_CLIENT.invoke(messages)
    content = getattr(response, "content", str(response))

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # Fallback: store raw content if it is not valid JSON
        existing = _read_kb_lines()
        new_line = f"RAW: {content}"
        if new_line not in existing:
            existing.append(new_line)
            _write_kb_lines(existing)
        return json.dumps({"status": "stored_raw", "raw": content}, indent=2)

    entities = data.get("entities", [])
    if not isinstance(entities, list):
        entities = []

    existing_lines = set(_read_kb_lines())
    added: list[str] = []

    for entity in entities:
        if not isinstance(entity, dict):
            continue
        etype = str(entity.get("type", "") or "").strip()
        value = str(entity.get("value", "") or "").strip()
        notes = str(entity.get("notes", "") or "").strip()
        if not value:
            continue
        line = f"{etype.upper() or 'UNKNOWN'} | {value}"
        if notes:
            line = f"{line} | {notes}"
        if line not in existing_lines:
            existing_lines.add(line)
            added.append(line)

    if added:
        all_lines = sorted(existing_lines)
        _write_kb_lines(all_lines)

    return json.dumps(
        {
            "status": "ok",
            "added": added,
            "kb_path": str(_kb_path()),
        },
        indent=2,
    )


@tool
def kb_get() -> str:
    """Return the current contents of the OSINT knowledge base (entities text file)."""
    lines = _read_kb_lines()
    if not lines:
        return "Knowledge base is empty."
    return "\n".join(lines)

