import json
from pathlib import Path
from typing import Any, List, Dict
from urllib.parse import urlparse
import re
from contextvars import ContextVar

from langchain.messages import SystemMessage, HumanMessage
from langchain.tools import tool

from llms.client_factory import ACTIVE_LLM_CLIENT
from tools.image_descriptor import describe_image
from tools.osint_multimedia import getEXIFdata


_KB_THREAD_ID_CTX: ContextVar[str] = ContextVar("kb_thread_id", default="global")


def _sanitize_thread_id(thread_id: str) -> str:
    if not thread_id:
        return "global"
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", thread_id.strip())
    return safe or "global"


def _current_thread_id() -> str:
    """
    Current thread id for KB namespacing.

    Set by main.tool_node per LangGraph thread invocation via set_kb_thread_id().
    """
    return _sanitize_thread_id(_KB_THREAD_ID_CTX.get())


def set_kb_thread_id(thread_id: str) -> None:
    """Set KB namespace for the current request context."""
    _KB_THREAD_ID_CTX.set(_sanitize_thread_id(thread_id))


@tool
def kb_current_thread_namespace() -> str:
    """Return the currently resolved KB thread namespace (for debugging thread-id wiring)."""
    return _current_thread_id()


def _kb_path() -> Path:
    """Return the path to the thread-scoped knowledge base entities text file."""
    root = Path(__file__).resolve().parent.parent
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    tid = _current_thread_id()
    thread_dir = data_dir / tid
    thread_dir.mkdir(parents=True, exist_ok=True)
    return thread_dir / "kb_entities.txt"


def _kb_config_path() -> Path:
    """Path to knowledge base config for dynamic entity type tag sets."""
    root = Path(__file__).resolve().parent.parent  # src/
    return root / "config" / "knowledge_base_config.json"


def _load_kb_config() -> Dict[str, Any]:
    """
    Load KB configuration (entity types etc.) from JSON.

    Reads from src/config/knowledge_base_config.json.
    Keeps only minimal safety fallback when config is missing/invalid.
    """
    minimal_fallback = {
        "entity_types": [{"type": "other", "description": "Fallback entity type."}],
        "relation_types": [{"type": "other_relation", "description": "Fallback relation type."}],
    }

    config_path = _kb_config_path()
    if not config_path.exists():
        return minimal_fallback

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return minimal_fallback

    entity_types = raw.get("entity_types", minimal_fallback["entity_types"])
    if not isinstance(entity_types, list):
        return minimal_fallback

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
        normalized_types = minimal_fallback["entity_types"]

    relation_types = raw.get("relation_types", minimal_fallback.get("relation_types", []))
    if not isinstance(relation_types, list):
        relation_types = minimal_fallback.get("relation_types", [])

    normalized_relations: List[Dict[str, str]] = []
    seen_rel: set[str] = set()
    for entry in relation_types:
        # Backwards compatible: allow ["mentions", "linked_to"] style.
        if isinstance(entry, str):
            rt = entry.strip()
            if not rt or rt in seen_rel:
                continue
            seen_rel.add(rt)
            normalized_relations.append({"type": rt, "description": ""})
            continue

        if not isinstance(entry, dict):
            continue

        rt = str(entry.get("type", "") or "").strip()
        if not rt or rt in seen_rel:
            continue

        desc = str(entry.get("description", "") or "").strip()
        seen_rel.add(rt)
        normalized_relations.append({"type": rt, "description": desc})

    if not normalized_relations:
        normalized_relations = minimal_fallback.get("relation_types", [])

    # Return normalized structure.
    return {
        "entity_types": normalized_types,
        "relation_types": normalized_relations,
    }


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
- If you detect images, classify them as type "image" and keep value as a stable URL/path/filename.
"""


def _is_url(value: str) -> bool:
    try:
        p = urlparse(value)
        return p.scheme in {"http", "https"} and bool(p.netloc)
    except Exception:
        return False


def _looks_like_image_ref(value: str) -> bool:
    v = value.strip().lower()
    image_exts = (".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff")
    return v.endswith(image_exts) or "/image" in v


def _enrich_image_notes(image_ref: str) -> str:
    """
    Best-effort enrichment for image entities.
    - URL: use describe_image
    - Local file path: try EXIF extraction
    """
    snippets: List[str] = []

    if _is_url(image_ref):
        try:
            desc_raw = describe_image(image_ref)
            desc = ""
            try:
                parsed = json.loads(desc_raw)
                desc = str(parsed.get("description", "") or "").strip()
            except Exception:
                desc = str(desc_raw).strip()
            if desc:
                snippets.append(f"description: {desc[:300]}")
        except Exception as e:
            snippets.append(f"description_error: {e}")
        return " | ".join(snippets)

    # local file / filename
    if _looks_like_image_ref(image_ref):
        try:
            exif = getEXIFdata(image_ref)
            if isinstance(exif, dict):
                img = exif.get("image", {}) if isinstance(exif.get("image", {}), dict) else {}
                cam = exif.get("camera", {}) if isinstance(exif.get("camera", {}), dict) else {}
                loc = exif.get("location", {}) if isinstance(exif.get("location", {}), dict) else {}

                summary_parts = []
                if img:
                    summary_parts.append(f"image_meta_keys={len(img)}")
                if cam:
                    summary_parts.append(f"camera_meta_keys={len(cam)}")
                if loc:
                    summary_parts.append(f"location_meta_keys={len(loc)}")
                if summary_parts:
                    snippets.append("exif: " + ", ".join(summary_parts))
        except Exception as e:
            snippets.append(f"exif_error: {e}")

    return " | ".join(snippets)


def _read_kb_lines() -> List[str]:
    path = _kb_path()
    if path.exists():
        return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]

    # Backward compatibility with old file naming in src/data root.
    legacy = path.parent.parent / f"kb_entities__{_current_thread_id()}.txt"
    if legacy.exists():
        return [line.rstrip("\n") for line in legacy.read_text(encoding="utf-8").splitlines() if line.strip()]

    # Backward compatibility with previous folder-per-type layout.
    legacy_folder = path.parent.parent / "kb_entities" / f"{_current_thread_id()}.txt"
    if legacy_folder.exists():
        return [line.rstrip("\n") for line in legacy_folder.read_text(encoding="utf-8").splitlines() if line.strip()]

    return []


def _write_kb_lines(lines: List[str]) -> None:
    path = _kb_path()
    content = "\n".join(lines) + "\n" if lines else ""
    path.write_text(content, encoding="utf-8")


def _build_entity_line(etype: str, value: str, notes: str = "") -> str:
    line = f"{etype.upper() or 'UNKNOWN'} | {value}"
    if notes:
        line = f"{line} | {notes}"
    return line


def _parse_entity_line(line: str) -> Dict[str, str]:
    """
    Parse KB entity line in format:
      TYPE | value | notes(optional)
    """
    parts = [p.strip() for p in line.split(" | ")]
    if len(parts) < 2:
        return {"type": "", "value": "", "notes": ""}
    etype = parts[0]
    value = parts[1]
    notes = " | ".join(parts[2:]).strip() if len(parts) > 2 else ""
    return {"type": etype, "value": value, "notes": notes}


def upsert_image_entity_description(image_ref: str, description: str) -> None:
    """
    Attach a generated description to an IMAGE entity in KB.

    - Creates the IMAGE entity if it does not exist.
    - Merges with existing notes for the same IMAGE + value.
    """
    ref = str(image_ref or "").strip()
    desc = str(description or "").strip()
    if not ref or not desc:
        return

    existing = _read_kb_lines()
    updated: List[str] = []
    found = False
    image_key = ref.lower()
    desc_note = f"image_description: {desc}"

    for line in existing:
        parsed = _parse_entity_line(line)
        etype = parsed.get("type", "").strip().upper()
        value = parsed.get("value", "").strip()
        notes = parsed.get("notes", "").strip()
        if etype == "IMAGE" and value.lower() == image_key:
            found = True
            if "image_description:" in notes:
                # Replace existing image_description while preserving other notes.
                other_notes = [n.strip() for n in notes.split(" | ") if n.strip() and not n.strip().startswith("image_description:")]
                merged_notes = " | ".join([*other_notes, desc_note]).strip(" |")
            else:
                merged_notes = f"{notes} | {desc_note}".strip(" |") if notes else desc_note
            updated.append(_build_entity_line("IMAGE", value, merged_notes))
        else:
            updated.append(line)

    if not found:
        updated.append(_build_entity_line("IMAGE", ref, desc_note))

    _write_kb_lines(sorted(set(updated)))


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
    response = ACTIVE_LLM_CLIENT.invoke(messages)
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

        # If type isn't explicitly image, infer image refs from value.
        if etype.lower() != "image" and _looks_like_image_ref(value):
            etype = "image"

        # Enrich image entities with visual/metadata insights.
        if etype.lower() == "image":
            enrichment = _enrich_image_notes(value)
            if enrichment:
                notes = f"{notes} | {enrichment}" if notes else enrichment

        line = _build_entity_line(etype, value, notes)
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


def _kb_edges_path() -> Path:
    """Return the path to the thread-scoped knowledge base edges file (jsonl)."""
    root = Path(__file__).resolve().parent.parent  # src/
    data_dir = root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    tid = _current_thread_id()
    thread_dir = data_dir / tid
    thread_dir.mkdir(parents=True, exist_ok=True)
    return thread_dir / "kb_edges.jsonl"


def _edge_key(from_type: str, from_value: str, relation_type: str, to_type: str, to_value: str) -> str:
    return f"{from_type}||{from_value}||{relation_type}||{to_type}||{to_value}"


def _load_edges_map() -> Dict[str, Dict[str, Any]]:
    path = _kb_edges_path()
    if not path.exists():
        # Backward compatibility with old file naming in src/data root.
        legacy = path.parent.parent / f"kb_edges__{_current_thread_id()}.jsonl"
        if legacy.exists():
            path = legacy
        else:
            # Backward compatibility with previous folder-per-type layout.
            legacy_folder = path.parent.parent / "kb_graph_edges" / f"{_current_thread_id()}.jsonl"
            if legacy_folder.exists():
                path = legacy_folder
            else:
                return {}

    edges: Dict[str, Dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue

        from_type = str(obj.get("from_type", "")).strip()
        from_value = str(obj.get("from_value", "")).strip()
        to_type = str(obj.get("to_type", "")).strip()
        to_value = str(obj.get("to_value", "")).strip()
        relation_type = str(obj.get("relation_type", "")).strip()
        if not (from_type and from_value and to_type and to_value and relation_type):
            continue

        key = _edge_key(from_type, from_value, relation_type, to_type, to_value)
        notes = obj.get("notes", "")
        if key not in edges:
            edges[key] = {
                "from_type": from_type,
                "from_value": from_value,
                "to_type": to_type,
                "to_value": to_value,
                "relation_type": relation_type,
                "notes_set": set(),
            }
        if isinstance(notes, str) and notes.strip():
            edges[key]["notes_set"].add(notes.strip())

    # Convert notes_set to list on save-time.
    return edges


def _save_edges_map(edges_map: Dict[str, Dict[str, Any]]) -> None:
    path = _kb_edges_path()
    # Write all edges deterministically for easier diffing/debugging.
    items = list(edges_map.values())
    items.sort(
        key=lambda e: (
            str(e.get("from_type", "")),
            str(e.get("from_value", "")),
            str(e.get("relation_type", "")),
            str(e.get("to_type", "")),
            str(e.get("to_value", "")),
        )
    )

    lines: List[str] = []
    for e in items:
        notes_set = e.get("notes_set", set())
        notes_list = sorted([n for n in notes_set if isinstance(n, str) and n.strip()])
        obj = {
            "from_type": e.get("from_type", ""),
            "from_value": e.get("from_value", ""),
            "relation_type": e.get("relation_type", ""),
            "to_type": e.get("to_type", ""),
            "to_value": e.get("to_value", ""),
            "notes": " | ".join(notes_list),
        }
        lines.append(json.dumps(obj, ensure_ascii=False))

    content = "\n".join(lines) + ("\n" if lines else "")
    path.write_text(content, encoding="utf-8")


def _relations_system_prompt(entity_types: List[Dict[str, str]], relation_types: List[Dict[str, str]]) -> str:
    allowed_rel = [t["type"] for t in relation_types if t.get("type")]
    allowed_rel_str = " | ".join(allowed_rel) if allowed_rel else "other_relation"

    rel_meanings = "\n".join(
        [f"- {r['type']}: {r.get('description', '').strip()}" for r in relation_types if r.get("type")]
    ).strip()
    if not rel_meanings:
        rel_meanings = "- other_relation: (unspecified)"

    # Reuse entity meanings so the model knows how to choose from entity_types.
    entity_meanings = "\n".join(
        [f"- {t['type']}: {t.get('description', '').strip()}" for t in entity_types if t.get("type")]
    ).strip()

    return f"""
You extract relationships (edges) between entities for a lightweight OSINT knowledge graph.

The input text may include mentions of multiple entity types. You should connect entities only when the text
explicitly supports the relationship.

Return a JSON object:
{{
  "relations": [
    {{
      "from_type": "entity type from allowed set",
      "from_value": "identifier value exactly as it appears/normalized",
      "to_type": "entity type from allowed set",
      "to_value": "identifier value exactly as it appears/normalized",
      "relation_type": "{allowed_rel_str}",
      "notes": "short evidence note (what in the text supports the edge)"
    }}
  ]
}}

Allowed entity types:
{entity_meanings}

Allowed relation types:
{rel_meanings}

Rules:
- Only output relations you can justify from the provided text.
- You should prefer the most specific relation_type possible; use "other_relation" only as a last resort.
- Use consistent direction: from_type/from_value should be the most specific or primary entity mentioned first.
"""


@tool
def kb_extract_relations(text: str) -> str:
    """Extract relationships between KB entities from investigation text and append to the knowledge graph edges.

    Stores edges in `src/data/kb_edges.jsonl` and de-duplicates by (from_type, from_value, relation_type, to_type, to_value).
    """
    if not text or not text.strip():
        return "No text provided for relation extraction."

    kb_config = _load_kb_config()
    entity_types = kb_config.get("entity_types", [])
    relation_types = kb_config.get("relation_types", [])
    if not isinstance(entity_types, list):
        entity_types = []
    if not isinstance(relation_types, list):
        relation_types = []

    # Normalize entity type entries into {type, description}.
    normalized_entity_types: List[Dict[str, str]] = []
    for entry in entity_types:
        if isinstance(entry, str):
            normalized_entity_types.append({"type": entry, "description": ""})
        elif isinstance(entry, dict) and entry.get("type"):
            normalized_entity_types.append(
                {"type": str(entry.get("type", "")).strip(), "description": str(entry.get("description", "")).strip()}
            )

    normalized_relation_types: List[Dict[str, str]] = []
    for entry in relation_types:
        if isinstance(entry, str):
            normalized_relation_types.append({"type": entry, "description": ""})
        elif isinstance(entry, dict) and entry.get("type"):
            normalized_relation_types.append(
                {"type": str(entry.get("type", "")).strip(), "description": str(entry.get("description", "")).strip()}
            )

    messages = [
        SystemMessage(
            content=_relations_system_prompt(normalized_entity_types, normalized_relation_types)
        ),
        HumanMessage(content=text),
    ]

    response = ACTIVE_LLM_CLIENT.invoke(messages)
    content = getattr(response, "content", str(response))

    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # If model output isn't valid JSON, don't destroy KB; store raw note as an edge-less raw record.
        edges = _load_edges_map()
        raw_key = _edge_key("other", "RAW", "other_relation", "other", content[:80])
        if raw_key not in edges:
            edges[raw_key] = {
                "from_type": "other",
                "from_value": "RAW",
                "to_type": "other",
                "to_value": content[:80],
                "relation_type": "other_relation",
                "notes_set": {content},
            }
            _save_edges_map(edges)
        return json.dumps({"status": "stored_raw_relations", "kb_path": str(_kb_edges_path())}, indent=2)

    relations = data.get("relations", [])
    if not isinstance(relations, list):
        relations = []

    allowed_rel_types = {str(r.get("type", "")).strip() for r in normalized_relation_types if isinstance(r, dict)}
    if not allowed_rel_types:
        allowed_rel_types = {"other_relation"}

    edges_map = _load_edges_map()
    added_keys: List[str] = []

    for rel in relations:
        if not isinstance(rel, dict):
            continue

        from_type = str(rel.get("from_type", "")).strip()
        from_value = str(rel.get("from_value", "")).strip()
        to_type = str(rel.get("to_type", "")).strip()
        to_value = str(rel.get("to_value", "")).strip()
        relation_type = str(rel.get("relation_type", "")).strip() or "mentions"
        notes = str(rel.get("notes", "")).strip()

        if not (from_type and from_value and to_type and to_value):
            continue

        if relation_type not in allowed_rel_types:
            relation_type = "mentions"

        key = _edge_key(from_type, from_value, relation_type, to_type, to_value)
        if key not in edges_map:
            edges_map[key] = {
                "from_type": from_type,
                "from_value": from_value,
                "to_type": to_type,
                "to_value": to_value,
                "relation_type": relation_type,
                "notes_set": set(),
            }
            added_keys.append(key)

        if notes:
            edges_map[key]["notes_set"].add(notes)

    if added_keys or relations:
        _save_edges_map(edges_map)

    return json.dumps(
        {"status": "ok", "added_edges": added_keys, "kb_path": str(_kb_edges_path())},
        indent=2,
    )


@tool
def kb_get_edges(limit: int = 50) -> str:
    """Return the current knowledge graph edges (relationships) from `kb_edges.jsonl`."""
    edges_map = _load_edges_map()
    if not edges_map:
        return "Knowledge graph edges are empty."

    edges_list = list(edges_map.values())
    edges_list.sort(
        key=lambda e: (
            str(e.get("from_type", "")),
            str(e.get("from_value", "")),
            str(e.get("relation_type", "")),
            str(e.get("to_type", "")),
            str(e.get("to_value", "")),
        )
    )

    sliced = edges_list[: max(1, limit)]
    lines: List[str] = []
    for e in sliced:
        notes_set = e.get("notes_set", set())
        notes = ""
        if isinstance(notes_set, set):
            notes_list = sorted([n for n in notes_set if isinstance(n, str) and n.strip()])
            if notes_list:
                notes = f" | evidence: {notes_list[0]}"
        lines.append(
            f"{e.get('relation_type')} | {e.get('from_type')}:{e.get('from_value')} -> {e.get('to_type')}:{e.get('to_value')}{notes}"
        )

    more = ""
    if len(edges_list) > len(sliced):
        more = f"\n... truncated; showing first {len(sliced)} of {len(edges_list)} edges."

    return "\n".join(lines) + more

