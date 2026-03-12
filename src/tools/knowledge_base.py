import json
from pathlib import Path
from typing import List

from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool

from llms.openai_client import OPENAI_CLIENT


def _kb_path() -> Path:
    """Return the path to the knowledge base text file."""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir / "kb_entities.txt"


def _read_kb_lines() -> List[str]:
    path = _kb_path()
    if not path.exists():
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_kb_lines(lines: List[str]) -> None:
    path = _kb_path()
    content = "\n".join(lines) + "\n" if lines else ""
    path.write_text(content, encoding="utf-8")


ENTITIES_SYSTEM_PROMPT = """
You extract a structured OSINT knowledge base from investigation notes.

Given free-form text about a target (person, organization, accounts, domains, etc.),
identify key entities and facts that should be stored for later reasoning and reporting.

Return a JSON object with this shape:
{
  "entities": [
    {
      "type": "person | organization | handle | account | domain | ip | location | other",
      "value": "short identifier (e.g. username, full name, domain)",
      "notes": "optional short note with key evidence or context"
    },
    ...
  ]
}

Guidelines:
- Be concise but include all important entities and aliases.
- Prefer stable identifiers (usernames, profile URLs, domains) over long sentences.
- Use `notes` to briefly capture the most important evidence or context.
"""


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

    messages = [
        SystemMessage(content=ENTITIES_SYSTEM_PROMPT),
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

