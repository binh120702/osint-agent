import json
import uuid
import hashlib
from pathlib import Path
from typing import Any, List, Dict
from urllib.parse import urlparse
import re
import os
from contextvars import ContextVar

from agent.messages import SystemMessage, HumanMessage
from agent.tool_decorator import tool

from llms.client_factory import ACTIVE_LLM_CLIENT
from tools.image_descriptor import describe_image
from tools.osint_multimedia import getEXIFdata

from neo4j import GraphDatabase


_KB_THREAD_ID_CTX: ContextVar[str] = ContextVar("kb_thread_id", default="global")
_KB_SUBJECT_ID_CTX: ContextVar[str] = ContextVar("kb_subject_id", default="")
_NEO4J_DRIVER = None


def get_neo4j_driver():
    """Get or initialize the Neo4j database driver connection pool."""
    global _NEO4J_DRIVER
    if _NEO4J_DRIVER is None:
        uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
        username = os.getenv("NEO4J_USERNAME", "neo4j")
        password = os.getenv("NEO4J_PASSWORD", "password")
        driver = GraphDatabase.driver(uri, auth=(username, password))
        
        # Try to initialize uniqueness constraint on Entity nodes
        try:
            with driver.session() as session:
                session.run(
                    "CREATE CONSTRAINT UNIQUE_ENTITY_PER_THREAD IF NOT EXISTS "
                    "FOR (e:Entity) REQUIRE (e.thread_id, e.type, e.value) IS UNIQUE"
                )
        except Exception as e:
            # Non-blocking warning (AuraDB or server versions may handle this differently)
            print(f"Neo4j constraint initialization warning: {e}")
            
        _NEO4J_DRIVER = driver
    return _NEO4J_DRIVER


def _sanitize_label(etype: str) -> str:
    """Sanitize entity type to form a safe Neo4j label name (PascalCase)."""
    clean = re.sub(r"[^a-zA-Z0-9]+", "", etype.strip())
    return clean.capitalize() or "Other"


def _sanitize_relationship_type(rel_type: str) -> str:
    """Sanitize relationship type to form a safe Neo4j relationship type (UPPER_SNAKE_CASE)."""
    clean = re.sub(r"[^a-zA-Z0-9_]+", "_", rel_type.strip()).upper()
    clean = clean.strip("_")
    if not clean or not clean[0].isalpha():
        return f"R_{clean}" if clean else "MENTIONS"
    return clean


def _sanitize_thread_id(thread_id: str) -> str:
    if not thread_id:
        return "global"
    safe = re.sub(r"[^a-zA-Z0-9._-]+", "_", thread_id.strip())
    return safe or "global"


def _current_thread_id() -> str:
    """
    Current thread id for KB namespacing.

    Set by agent.loop per request context via set_kb_thread_id().
    """
    return _sanitize_thread_id(_KB_THREAD_ID_CTX.get())


def set_kb_thread_id(thread_id: str) -> None:
    """Set KB namespace for the current request context."""
    _KB_THREAD_ID_CTX.set(_sanitize_thread_id(thread_id))


def set_kb_subject_id(subject_id: str | None) -> None:
    """Set the shared subject namespace for the current request, if any."""
    _KB_SUBJECT_ID_CTX.set(_sanitize_thread_id(subject_id) if subject_id else "")


def _current_subject_id() -> str:
    return _KB_SUBJECT_ID_CTX.get()


def current_kb_namespace() -> str:
    """Return the shared subject namespace or legacy thread namespace."""
    return _current_subject_id() or _current_thread_id()


@tool
def kb_current_thread_namespace() -> str:
    """Return the currently resolved KB thread namespace (for debugging thread-id wiring)."""
    return current_kb_namespace()


def _mirror_entities_to_file(thread_id: str) -> None:
    """Sync entities from Neo4j back to local files for Next.js UI compatibility."""
    try:
        driver = get_neo4j_driver()
        query = """
        MATCH (e:Entity {thread_id: $thread_id})
        RETURN e.type AS type, e.value AS value, e.notes AS notes
        ORDER BY type, value
        """
        with driver.session() as session:
            result = session.run(query, thread_id=thread_id)
            lines = []
            for record in result:
                lines.append(_build_entity_line(record["type"], record["value"], record["notes"] or ""))
            
            root = Path(__file__).resolve().parent.parent
            data_dir = root / "data" / thread_id
            data_dir.mkdir(parents=True, exist_ok=True)
            entities_file = data_dir / "kb_entities.txt"
            
            content = "\n".join(lines) + "\n" if lines else ""
            entities_file.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"Error mirroring entities to file: {e}")


def _mirror_relations_to_file(thread_id: str) -> None:
    """Sync relationships from Neo4j back to JSONL file for Next.js UI compatibility."""
    try:
        driver = get_neo4j_driver()
        query = """
        MATCH (from:Entity {thread_id: $thread_id})-[r]->(to:Entity {thread_id: $thread_id})
        WHERE coalesce(r.status, 'active') <> 'removed'
        RETURN from.type AS from_type, from.value AS from_value,
               type(r) AS relation_type,
               to.type AS to_type, to.value AS to_value,
               r.notes AS notes
        ORDER BY from_type, from_value, relation_type, to_type, to_value
        """
        with driver.session() as session:
            result = session.run(query, thread_id=thread_id)
            lines = []
            for record in result:
                notes = record["notes"] or ""
                notes_list = [n.strip() for n in notes.split(" | ") if n.strip()]
                obj = {
                    "from_type": record["from_type"],
                    "from_value": record["from_value"],
                    "relation_type": record["relation_type"].lower(),
                    "to_type": record["to_type"],
                    "to_value": record["to_value"],
                    "notes": " | ".join(notes_list)
                }
                lines.append(json.dumps(obj, ensure_ascii=False))
            
            root = Path(__file__).resolve().parent.parent
            data_dir = root / "data" / thread_id
            data_dir.mkdir(parents=True, exist_ok=True)
            edges_file = data_dir / "kb_edges.jsonl"
            
            content = "\n".join(lines) + "\n" if lines else ""
            edges_file.write_text(content, encoding="utf-8")
    except Exception as e:
        print(f"Error mirroring relations to file: {e}")


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

    normalized_types: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for entry in entity_types:
        if isinstance(entry, str):
            t = entry.strip()
            if not t or t in seen:
                continue
            seen.add(t)
            normalized_types.append({"type": t, "description": "", "metadata_fields": []})
            continue

        if not isinstance(entry, dict):
            continue

        t = str(entry.get("type", "") or "").strip()
        if not t or t in seen:
            continue

        desc = str(entry.get("description", "") or "").strip()
        seen.add(t)
        metadata_fields = entry.get("metadata_fields", [])
        if not isinstance(metadata_fields, list):
            metadata_fields = []
        normalized_types.append({"type": t, "description": desc, "metadata_fields": metadata_fields})

    if not normalized_types:
        normalized_types = minimal_fallback["entity_types"]

    relation_types = raw.get("relation_types", minimal_fallback.get("relation_types", []))
    if not isinstance(relation_types, list):
        relation_types = minimal_fallback.get("relation_types", [])

    normalized_relations: List[Dict[str, str]] = []
    seen_rel: set[str] = set()
    for entry in relation_types:
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

    return {
        "entity_types": normalized_types,
        "relation_types": normalized_relations,
    }


def _knowledge_agent_system_prompt(entity_types: List[Dict[str, str]], relation_types: List[Dict[str, str]]) -> str:
    allowed_entities = [t["type"] for t in entity_types if t.get("type")]
    allowed_entities_str = " | ".join(allowed_entities) if allowed_entities else "other"
    
    allowed_relations = [t["type"] for t in relation_types if t.get("type")]
    allowed_relations_str = " | ".join(allowed_relations) if allowed_relations else "other_relation"
    
    entity_meanings = "\n".join(
        [
            f"- {t['type']}: {t.get('description', '').strip()}"
            + (f" Metadata fields: {', '.join(str(field.get('name', field)) if isinstance(field, dict) else str(field) for field in t.get('metadata_fields', []))}." if t.get('metadata_fields') else "")
            for t in entity_types if t.get("type")
        ]
    ).strip()
    
    relation_meanings = "\n".join(
        [f"- {r['type']}: {r.get('description', '').strip()}" for r in relation_types if r.get("type")]
    ).strip()

    return f"""
You are a specialized Knowledge Agent. Your task is to extract a structured OSINT knowledge base and graph from the provided investigation text.

Analyze the input text to identify key entities and the relationships between them. You must strictly use the allowed entity types and relationship types below.

Allowed Entity Types:
{allowed_entities_str}

Entity Type Meanings & Descriptions:
{entity_meanings}

Allowed Relationship Types:
{allowed_relations_str}

Relationship Type Meanings & Descriptions:
{relation_meanings}

Return a single JSON object containing both entities and relations using this exact schema:
{{
  "entities": [
    {{
      "type": "one of the allowed entity types",
      "value": "short identifier (e.g. username, full name, domain, URL)",
      "notes": "optional short note with key evidence, context, or timestamps",
      "metadata": {{
        "field_name": "source-supported metadata value; use only fields defined for this entity type"
      }}
    }}
  ],
  "relations": [
    {{
      "from_type": "entity type of the source entity",
      "from_value": "identifier value of the source entity exactly matching a value in the entities list",
      "to_type": "entity type of the target entity",
      "to_value": "identifier value of the target entity exactly matching a value in the entities list",
      "relation_type": "one of the allowed relationship types",
      "notes": "short evidence note explaining what in the text supports this relationship"
    }}
  ]
}}

Extraction Rules:
1. Be concise but complete. Extract all key details.
2. Values should be stable identifiers where possible (e.g., usernames, domain names, URLs, email addresses) rather than conversational text.
3. Only extract relations that are explicitly supported by the text.
4. Ensure the source and target values in the "relations" array exist exactly in the "entities" array.
5. If you detect images, classify them as type "image" and use their URL, path, or filename as the value.
6. Extract metadata only when the input explicitly supports it. Do not infer or invent metadata.
7. Metadata keys must be one of the fields listed for the entity type. Use arrays only when multiple distinct values are supported.
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


def _build_entity_line(etype: str, value: str, notes: str = "") -> str:
    line = f"{etype.upper() or 'UNKNOWN'} | {value}"
    if notes:
        line = f"{line} | {notes}"
    return line


def upsert_image_entity_description(image_ref: str, description: str) -> None:
    """
    Attach a generated description to an IMAGE entity in Neo4j.

    - Creates the IMAGE entity if it does not exist.
    - Merges with existing notes for the same IMAGE + value.
    """
    ref = str(image_ref or "").strip()
    desc = str(description or "").strip()
    if not ref or not desc:
        return

    thread_id = _current_thread_id()
    desc_note = f"image_description: {desc}"

    driver = get_neo4j_driver()
    with driver.session() as session:
        # Get existing notes
        result = session.run(
            "MATCH (e:Entity {thread_id: $thread_id, type: 'image', value: $value}) RETURN e.notes AS notes",
            thread_id=thread_id, value=ref
        )
        record = result.single()
        notes = record["notes"] if record else None

        if notes:
            if "image_description:" in notes:
                # Replace existing image_description while preserving other notes.
                other_notes = [n.strip() for n in notes.split(" | ") if n.strip() and not n.strip().startswith("image_description:")]
                merged_notes = " | ".join([*other_notes, desc_note]).strip(" |")
            else:
                merged_notes = f"{notes} | {desc_note}".strip(" |")
        else:
            merged_notes = desc_note

        # Upsert node
        session.run(
            "MERGE (e:Entity {thread_id: $thread_id, type: 'image', value: $value}) "
            "SET e:Image, e.notes = $notes, e.updated_at = timestamp()",
            thread_id=thread_id, value=ref, notes=merged_notes
        )
    _mirror_entities_to_file(thread_id)







@tool
def kb_get() -> str:
    """Return the current contents of the OSINT knowledge base (Neo4j Entity nodes)."""
    thread_id = current_kb_namespace()
    driver = get_neo4j_driver()
    query = """
    MATCH (e:Entity {thread_id: $thread_id})
    RETURN e.type AS type, e.value AS value, e.notes AS notes
    ORDER BY type, value
    """
    with driver.session() as session:
        result = session.run(query, thread_id=thread_id)
        lines = []
        for record in result:
            lines.append(_build_entity_line(record["type"], record["value"], record["notes"] or ""))
        
        if not lines:
            return "Knowledge base is empty."
        return "\n".join(lines)


def _decode_metadata(raw: Any) -> dict:
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}


@tool
def kb_search_entities(query: str = "", entity_type: str = "", limit: int = 25) -> str:
    """Search entities in the active knowledge-base namespace before editing them.

    Args:
        query: Case-insensitive text matched against entity type, value, or notes.
        entity_type: Optional exact entity type filter.
        limit: Maximum number of results to return.
    """
    namespace = current_kb_namespace()
    safe_limit = max(1, min(int(limit or 25), 100))
    query_text = str(query or "").strip().lower()
    type_text = str(entity_type or "").strip()
    driver = get_neo4j_driver()
    with driver.session() as session:
        result = session.run(
            "MATCH (e:Entity {thread_id: $namespace}) "
            "WHERE ($entity_type = '' OR e.type = $entity_type) "
            "AND ($query = '' OR toLower(e.type) CONTAINS $query "
            "OR toLower(e.value) CONTAINS $query OR toLower(coalesce(e.notes, '')) CONTAINS $query) "
            "RETURN e.type AS type, e.value AS value, e.notes AS notes, "
            "e.metadata_json AS metadata_json ORDER BY e.type, e.value LIMIT $limit",
            namespace=namespace, entity_type=type_text, query=query_text, limit=safe_limit,
        )
        matches = [
            {
                "type": record["type"],
                "value": record["value"],
                "notes": record["notes"] or "",
                "metadata": _decode_metadata(record["metadata_json"]),
            }
            for record in result
        ]
    return json.dumps({"namespace": namespace, "count": len(matches), "entities": matches}, ensure_ascii=False, indent=2)


@tool
def kb_search_relationships(
    query: str = "",
    from_type: str = "",
    from_value: str = "",
    relation_type: str = "",
    to_type: str = "",
    to_value: str = "",
    limit: int = 50,
) -> str:
    """Search active relationships in the active knowledge-base namespace.

    Args:
        query: Case-insensitive text matched against endpoint values, relation type, or notes.
        from_type: Optional exact source entity type.
        from_value: Optional exact source entity value.
        relation_type: Optional relationship type filter.
        to_type: Optional exact target entity type.
        to_value: Optional exact target entity value.
        limit: Maximum number of results to return.
    """
    namespace = current_kb_namespace()
    safe_limit = max(1, min(int(limit or 50), 200))
    params = {
        "namespace": namespace,
        "query": str(query or "").strip().lower(),
        "from_type": str(from_type or "").strip(),
        "from_value": str(from_value or "").strip(),
        "relation_type": _sanitize_relationship_type(relation_type) if relation_type else "",
        "to_type": str(to_type or "").strip(),
        "to_value": str(to_value or "").strip(),
        "limit": safe_limit,
    }
    with get_neo4j_driver().session() as session:
        result = session.run(
            "MATCH (from:Entity {thread_id: $namespace})-[r]->(to:Entity {thread_id: $namespace}) "
            "WHERE coalesce(r.status, 'active') <> 'removed' "
            "AND ($from_type = '' OR from.type = $from_type) "
            "AND ($from_value = '' OR from.value = $from_value) "
            "AND ($relation_type = '' OR type(r) = $relation_type) "
            "AND ($to_type = '' OR to.type = $to_type) "
            "AND ($to_value = '' OR to.value = $to_value) "
            "AND ($query = '' OR toLower(from.value) CONTAINS $query "
            "OR toLower(to.value) CONTAINS $query OR toLower(type(r)) CONTAINS $query "
            "OR toLower(coalesce(r.notes, '')) CONTAINS $query) "
            "RETURN from.type AS from_type, from.value AS from_value, type(r) AS relation_type, "
            "to.type AS to_type, to.value AS to_value, r.notes AS notes "
            "ORDER BY from_type, from_value, relation_type, to_type, to_value LIMIT $limit",
            **params,
        )
        matches = [
            {
                "from_type": record["from_type"], "from_value": record["from_value"],
                "relation_type": record["relation_type"].lower(),
                "to_type": record["to_type"], "to_value": record["to_value"],
                "notes": record["notes"] or "",
            }
            for record in result
        ]
    return json.dumps({"namespace": namespace, "count": len(matches), "relationships": matches}, ensure_ascii=False, indent=2)


@tool
def kb_update_entity(type: str, value: str, notes: str = "", metadata: dict | None = None) -> str:
    """Update notes or structured metadata on one exact existing entity.

    Search first and use the exact type and value returned by kb_search_entities. Entity identity cannot be renamed by this tool.

    Args:
        type: Exact entity type.
        value: Exact entity value.
        notes: Optional replacement for the entity notes. Omit by passing an empty string to preserve existing notes.
        metadata: Optional metadata fields to merge into the existing metadata map.
    """
    namespace = current_kb_namespace()
    entity_type = str(type or "").strip()
    entity_value = str(value or "").strip()
    if not entity_type or not entity_value:
        return json.dumps({"status": "error", "error": "type and value are required"})
    metadata = metadata if isinstance(metadata, dict) else {}
    with get_neo4j_driver().session() as session:
        record = session.run(
            "MATCH (e:Entity {thread_id: $namespace, type: $type, value: $value}) "
            "RETURN e.notes AS notes, e.metadata_json AS metadata_json",
            namespace=namespace, type=entity_type, value=entity_value,
        ).single()
        if not record:
            return json.dumps({"status": "not_found", "namespace": namespace, "type": entity_type, "value": entity_value})
        current_metadata = _decode_metadata(record["metadata_json"])
        merged_metadata = {**current_metadata, **metadata}
        set_parts = ["e.updated_at = timestamp()"]
        params: dict[str, Any] = {"namespace": namespace, "type": entity_type, "value": entity_value}
        if notes:
            set_parts.append("e.notes = $notes")
            params["notes"] = notes.strip()
        if metadata:
            set_parts.append("e.metadata_json = $metadata_json")
            params["metadata_json"] = json.dumps(merged_metadata, ensure_ascii=False)
        if len(set_parts) == 1:
            return json.dumps({"status": "unchanged", "namespace": namespace, "type": entity_type, "value": entity_value})
        updated = session.run(
            f"MATCH (e:Entity {{thread_id: $namespace, type: $type, value: $value}}) "
            f"SET {', '.join(set_parts)} "
            "RETURN e.type AS type, e.value AS value, e.notes AS notes, e.metadata_json AS metadata_json",
            **params,
        ).single()
    _mirror_entities_to_file(namespace)
    return json.dumps({
        "status": "updated", "namespace": namespace,
        "entity": {"type": updated["type"], "value": updated["value"], "notes": updated["notes"] or "", "metadata": _decode_metadata(updated["metadata_json"])},
    }, ensure_ascii=False, indent=2)


@tool
def kb_upsert_relationship(
    from_type: str, from_value: str, relation_type: str, to_type: str, to_value: str, notes: str = ""
) -> str:
    """Create or update one relationship between exact existing entities.

    Search both entities and the relationship first. This tool will not create missing endpoint entities.
    """
    namespace = current_kb_namespace()
    source_type, source_value = str(from_type or "").strip(), str(from_value or "").strip()
    target_type, target_value = str(to_type or "").strip(), str(to_value or "").strip()
    rel_type = _sanitize_relationship_type(relation_type)
    if not all([source_type, source_value, target_type, target_value, relation_type]):
        return json.dumps({"status": "error", "error": "all endpoint and relationship fields are required"})
    with get_neo4j_driver().session() as session:
        endpoints = session.run(
            "MATCH (e:Entity {thread_id: $namespace}) "
            "WHERE (e.type = $source_type AND e.value = $source_value) "
            "OR (e.type = $target_type AND e.value = $target_value) "
            "RETURN e.type AS type, e.value AS value",
            namespace=namespace, source_type=source_type, source_value=source_value,
            target_type=target_type, target_value=target_value,
        )
        endpoint_keys = {(row["type"], row["value"]) for row in endpoints}
        if (source_type, source_value) not in endpoint_keys or (target_type, target_value) not in endpoint_keys:
            return json.dumps({"status": "not_found", "error": "both endpoint entities must already exist", "namespace": namespace})
        updated = session.run(
            f"MATCH (from:Entity {{thread_id: $namespace, type: $source_type, value: $source_value}}) "
            f"MATCH (to:Entity {{thread_id: $namespace, type: $target_type, value: $target_value}}) "
            f"MERGE (from)-[r:{rel_type} {{thread_id: $namespace}}]->(to) "
            "SET r.status = 'active', r.updated_at = timestamp(), "
            "r.notes = CASE WHEN $notes = '' THEN coalesce(r.notes, '') ELSE $notes END "
            "RETURN from.type AS from_type, from.value AS from_value, type(r) AS relation_type, "
            "to.type AS to_type, to.value AS to_value, r.notes AS notes",
            namespace=namespace, source_type=source_type, source_value=source_value,
            target_type=target_type, target_value=target_value, notes=str(notes or "").strip(),
        ).single()
    _mirror_relations_to_file(namespace)
    return json.dumps({"status": "upserted", "namespace": namespace, "relationship": dict(updated)}, ensure_ascii=False, indent=2)


@tool
def kb_remove_relationship(
    from_type: str, from_value: str, relation_type: str, to_type: str, to_value: str, reason: str = ""
) -> str:
    """Soft-remove one exact relationship while preserving its audit history.

    Search first and use exact endpoint identities. Removed relationships are hidden from normal searches and can be restored with kb_upsert_relationship.
    """
    namespace = current_kb_namespace()
    rel_type = _sanitize_relationship_type(relation_type)
    with get_neo4j_driver().session() as session:
        removed = session.run(
            f"MATCH (from:Entity {{thread_id: $namespace, type: $from_type, value: $from_value}})"
            f"-[r:{rel_type} {{thread_id: $namespace}}]->"
            f"(to:Entity {{thread_id: $namespace, type: $to_type, value: $to_value}}) "
            "WHERE coalesce(r.status, 'active') <> 'removed' "
            "SET r.status = 'removed', r.removed_at = timestamp(), r.removal_reason = $reason "
            "RETURN from.type AS from_type, from.value AS from_value, type(r) AS relation_type, "
            "to.type AS to_type, to.value AS to_value, r.removal_reason AS removal_reason",
            namespace=namespace, from_type=str(from_type or "").strip(), from_value=str(from_value or "").strip(),
            to_type=str(to_type or "").strip(), to_value=str(to_value or "").strip(), reason=str(reason or "").strip(),
        ).single()
    if not removed:
        return json.dumps({"status": "not_found", "namespace": namespace})
    _mirror_relations_to_file(namespace)
    return json.dumps({"status": "removed", "namespace": namespace, "relationship": dict(removed)}, ensure_ascii=False, indent=2)


def _edge_key(from_type: str, from_value: str, relation_type: str, to_type: str, to_value: str) -> str:
    return f"{from_type}||{from_value}||{relation_type}||{to_type}||{to_value}"



@tool
def knowledge_agent(text: str, source_url: str = "", source_title: str = "") -> str:
    """Analyze investigation findings to extract, resolve, and save structured entities and relationships to the knowledge base.
    
    Args:
        text: Raw observations, notes, or tool outputs to process.
        source_url: Optional source URL or document reference for the observations.
        source_title: Optional source title.
    """
    if not text or not text.strip():
        return "No text provided to the Knowledge Agent."

    kb_config = _load_kb_config()
    entity_types = kb_config.get("entity_types", [])
    relation_types = kb_config.get("relation_types", [])
    if not isinstance(entity_types, list):
        entity_types = []
    if not isinstance(relation_types, list):
        relation_types = []

    # Normalize entity types
    normalized_entities: List[Dict[str, Any]] = []
    for entry in entity_types:
        if isinstance(entry, str):
            normalized_entities.append({"type": entry, "description": "", "metadata_fields": []})
        elif isinstance(entry, dict) and entry.get("type"):
            normalized_entities.append(
                {
                    "type": str(entry.get("type", "")).strip(),
                    "description": str(entry.get("description", "")).strip(),
                    "metadata_fields": entry.get("metadata_fields", []) if isinstance(entry.get("metadata_fields", []), list) else [],
                }
            )

    # Normalize relation types
    normalized_relations: List[Dict[str, str]] = []
    for entry in relation_types:
        if isinstance(entry, str):
            normalized_relations.append({"type": entry, "description": ""})
        elif isinstance(entry, dict) and entry.get("type"):
            normalized_relations.append(
                {"type": str(entry.get("type", "")).strip(), "description": str(entry.get("description", "")).strip()}
            )

    messages = [
        SystemMessage(content=_knowledge_agent_system_prompt(normalized_entities, normalized_relations)),
        HumanMessage(content=text),
    ]
    
    response = ACTIVE_LLM_CLIENT.invoke(messages)
    content = getattr(response, "content", str(response))
    if not isinstance(content, str):
        # Some providers return structured content blocks instead of a plain
        # string. Preserve the response in a form the parser can inspect.
        content = json.dumps(content, ensure_ascii=False, default=str)
    
    thread_id = current_kb_namespace()
    subject_id = _current_subject_id()
    driver = get_neo4j_driver()

    try:
        # LLM might wrap JSON in markdown block. Clean it if necessary.
        cleaned_content = content.strip()
        if cleaned_content.startswith("```json"):
            cleaned_content = cleaned_content[7:]
        if cleaned_content.endswith("```"):
            cleaned_content = cleaned_content[:-3]
        cleaned_content = cleaned_content.strip()

        data = json.loads(cleaned_content)
        # Models occasionally return a JSON-encoded string containing the
        # actual object (for example, \"{\\\"entities\\\": []}\"). Unwrap it
        # once before accessing object fields.
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise ValueError("Knowledge Agent response must be a JSON object")
    except (json.JSONDecodeError, ValueError, TypeError):
        # Fallback: store raw content in Neo4j if it is not valid JSON
        with driver.session() as session:
            session.run(
                "MERGE (e:Entity {thread_id: $thread_id, type: 'RAW', value: $value}) "
                "SET e:Raw, e.notes = $notes, e.created_at = timestamp()",
                thread_id=thread_id, value=content[:200], notes=content
            )
            if subject_id:
                session.run(
                    "CREATE (ev:Evidence {evidence_id: $evidence_id, subject_id: $subject_id, "
                    "thread_id: $thread_id, claim: $claim, source_url: $source_url, "
                    "source_title: $source_title, confidence: 0.5, status: 'pending', created_at: timestamp()})",
                    evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}", subject_id=subject_id,
                    thread_id=thread_id, claim=content, source_url=source_url, source_title=source_title,
                )
        return json.dumps({"status": "stored_raw", "raw": content}, indent=2)

    extracted_entities = data.get("entities", [])
    extracted_relations = data.get("relations", [])

    if not isinstance(extracted_entities, list):
        extracted_entities = []
    if not isinstance(extracted_relations, list):
        extracted_relations = []

    # Process Entities
    processed_entities = []
    metadata_fields_by_type = {
        item["type"]: {
            str(field.get("name", field)).strip()
            for field in item.get("metadata_fields", [])
            if (isinstance(field, str) and field.strip()) or (isinstance(field, dict) and field.get("name"))
        }
        for item in normalized_entities
        if item.get("type")
    }
    for entity in extracted_entities:
        if not isinstance(entity, dict):
            continue
        etype = str(entity.get("type", "") or "").strip()
        value = str(entity.get("value", "") or "").strip()
        notes = str(entity.get("notes", "") or "").strip()
        if not value:
            continue

        if etype.lower() != "image" and _looks_like_image_ref(value):
            etype = "image"

        if etype.lower() == "image":
            enrichment = _enrich_image_notes(value)
            if enrichment:
                notes = f"{notes} | {enrichment}" if notes else enrichment

        allowed_metadata = metadata_fields_by_type.get(etype, set())
        raw_metadata = entity.get("metadata", {})
        metadata: Dict[str, List[Any]] = {}
        if isinstance(raw_metadata, dict):
            for key, raw_value in raw_metadata.items():
                key = str(key).strip()
                if key not in allowed_metadata:
                    continue
                values = raw_value if isinstance(raw_value, list) else [raw_value]
                clean_values = []
                for value_item in values:
                    if isinstance(value_item, (str, int, float, bool)) and str(value_item).strip():
                        clean_values.append(value_item)
                if clean_values:
                    metadata[key] = clean_values

        processed_entities.append({
            "type": etype,
            "value": value,
            "notes": notes,
            "metadata": metadata,
        })

    # Group by label to execute dynamic Cypher batch updates safely
    entities_by_label = {}
    for item in processed_entities:
        label = _sanitize_label(item["type"])
        entities_by_label.setdefault((item["type"], label), []).append(item)

    added_entities_info = []
    with driver.session() as session:
        for (etype, label), batch in entities_by_label.items():
            query = f"""
            UNWIND $batch AS item
            MERGE (e:Entity {{thread_id: $thread_id, type: $type, value: item.value}})
            ON CREATE SET e.notes = item.notes, e.created_at = timestamp()
            ON MATCH SET e.notes = CASE
                WHEN item.notes = '' THEN e.notes
                WHEN e.notes IS NULL OR e.notes = '' THEN item.notes
                WHEN NOT e.notes CONTAINS item.notes THEN e.notes + ' | ' + item.notes
                ELSE e.notes
            END
            SET e:{label}
            RETURN e.type AS type, e.value AS value
            """
            result = session.run(query, thread_id=thread_id, type=etype, batch=batch)
            for record in result:
                added_entities_info.append(f"{record['type'].upper()} | {record['value']}")

    allowed_rel_types = {str(r.get("type", "")).strip() for r in normalized_relations}
    if not allowed_rel_types:
        allowed_rel_types = {"other_relation"}

    relations_by_group = {}
    for rel in extracted_relations:
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

        from_label = _sanitize_label(from_type)
        to_label = _sanitize_label(to_type)
        rel_type = _sanitize_relationship_type(relation_type)

        group_key = (from_type, from_label, to_type, to_label, rel_type)
        relations_by_group.setdefault(group_key, []).append({
            "from_value": from_value,
            "to_value": to_value,
            "notes": notes
        })

    added_edges = []
    with driver.session() as session:
        for (from_type, from_label, to_type, to_label, rel_type), batch in relations_by_group.items():
            query = f"""
            UNWIND $batch AS item
            MERGE (from:Entity {{thread_id: $thread_id, type: $from_type, value: item.from_value}})
            MERGE (to:Entity {{thread_id: $thread_id, type: $to_type, value: item.to_value}})
            MERGE (from)-[r:{rel_type} {{thread_id: $thread_id}}]->(to)
            ON CREATE SET r.notes = item.notes, r.created_at = timestamp()
            ON MATCH SET r.notes = CASE
                WHEN item.notes = '' THEN r.notes
                WHEN r.notes IS NULL OR r.notes = '' THEN item.notes
                WHEN NOT r.notes CONTAINS item.notes THEN r.notes + ' | ' + item.notes
                ELSE r.notes
            END
            SET from:{from_label}, to:{to_label}
            RETURN from.type AS from_type, from.value AS from_value,
                   to.type AS to_type, to.value AS to_value
            """
            result = session.run(
                query,
                thread_id=thread_id,
                from_type=from_type,
                to_type=to_type,
                batch=batch
            )
            for record in result:
                added_edges.append(
                    f"{rel_type} | {record['from_type']}:{record['from_value']} -> {record['to_type']}:{record['to_value']}"
                )

        if subject_id:
            evidence_id = f"EVD-{uuid.uuid4().hex[:12].upper()}"
            session.run(
                "CREATE (ev:Evidence {evidence_id: $evidence_id, subject_id: $subject_id, "
                "thread_id: $thread_id, claim: $claim, source_url: $source_url, "
                "source_title: $source_title, confidence: 0.5, status: 'pending', created_at: timestamp()})",
                evidence_id=evidence_id, subject_id=subject_id,
                thread_id=thread_id, claim=text[:12000], source_url=source_url, source_title=source_title,
            )
            values = [item["value"] for item in processed_entities]
            if values:
                session.run(
                    "MATCH (ev:Evidence {evidence_id: $evidence_id}) "
                    "MATCH (e:Entity {thread_id: $thread_id}) WHERE e.value IN $values "
                    "MERGE (ev)-[:SUPPORTS]->(e)",
                    evidence_id=evidence_id, thread_id=thread_id, values=values,
                )

            # Metadata is proposed as field-level evidence so each value can be
            # reviewed independently and retain its source provenance.
            for item in processed_entities:
                for metadata_key, values in item["metadata"].items():
                    for proposed_value in values:
                        metadata_evidence_id = "EVD-" + hashlib.sha256(
                            f"{subject_id}|{thread_id}|{item['type']}|{item['value']}|{metadata_key}|{proposed_value}|{source_url}|{source_title}".encode("utf-8")
                        ).hexdigest()[:12].upper()
                        metadata_claim = f"{item['type']}:{item['value']} has {metadata_key} = {proposed_value}"
                        session.run(
                            "MERGE (ev:Evidence {evidence_id: $evidence_id}) "
                            "ON CREATE SET ev.subject_id = $subject_id, ev.thread_id = $thread_id, "
                            "ev.kind = 'entity_metadata', ev.entity_type = $entity_type, "
                            "ev.entity_value = $entity_value, ev.metadata_key = $metadata_key, "
                            "ev.proposed_value = $proposed_value, ev.claim = $claim, "
                            "ev.source_url = $source_url, ev.source_title = $source_title, "
                            "ev.confidence = 0.5, ev.status = 'pending', ev.created_at = timestamp() "
                            "WITH ev "
                            "MATCH (entity:Entity {thread_id: $subject_id, type: $entity_type, value: $entity_value}) "
                            "MERGE (ev)-[:SUPPORTS]->(entity)",
                            evidence_id=metadata_evidence_id, subject_id=subject_id, thread_id=thread_id,
                            entity_type=item["type"], entity_value=item["value"], metadata_key=metadata_key,
                            proposed_value=json.dumps(proposed_value, ensure_ascii=False), claim=metadata_claim[:12000],
                            source_url=source_url, source_title=source_title,
                        )

    # Sync entities and relations to local files for Next.js UI compatibility
    _mirror_entities_to_file(thread_id)
    _mirror_relations_to_file(thread_id)

    return json.dumps(
        {
            "status": "ok",
            "added_entities": added_entities_info,
            "added_edges": added_edges,
            "neo4j": True,
        },
        indent=2,
    )


@tool
def kb_get_edges(limit: int = 50) -> str:
    """Return the current knowledge graph edges (relationships) from Neo4j."""
    thread_id = current_kb_namespace()
    driver = get_neo4j_driver()
    query = """
    MATCH (from:Entity {thread_id: $thread_id})-[r]->(to:Entity {thread_id: $thread_id})
    WHERE coalesce(r.status, 'active') <> 'removed'
    RETURN from.type AS from_type, from.value AS from_value,
           type(r) AS relation_type,
           to.type AS to_type, to.value AS to_value,
           r.notes AS notes
    ORDER BY from_type, from_value, relation_type, to_type, to_value
    """
    with driver.session() as session:
        result = session.run(query, thread_id=thread_id)
        edges_list = []
        for record in result:
            edges_list.append({
                "from_type": record["from_type"],
                "from_value": record["from_value"],
                "relation_type": record["relation_type"],
                "to_type": record["to_type"],
                "to_value": record["to_value"],
                "notes": record["notes"] or ""
            })

        if not edges_list:
            return "Knowledge graph edges are empty."

        sliced = edges_list[: max(1, limit)]
        lines: List[str] = []
        for e in sliced:
            notes = e["notes"].strip()
            evidence = ""
            if notes:
                notes_list = [n.strip() for n in notes.split(" | ") if n.strip()]
                if notes_list:
                    evidence = f" | evidence: {notes_list[0]}"
            
            lines.append(
                f"{e['relation_type'].lower()} | {e['from_type']}:{e['from_value']} -> {e['to_type']}:{e['to_value']}{evidence}"
            )

        more = ""
        if len(edges_list) > len(sliced):
            more = f"\n... truncated; showing first {len(sliced)} of {len(edges_list)} edges."

        return "\n".join(lines) + more


def get_subject_context(subject_id: str, limit: int = 40) -> str:
    """Build a compact context block from confirmed subject knowledge."""
    driver = get_neo4j_driver()
    lines: list[str] = []
    with driver.session() as session:
        entities = session.run(
            "MATCH (e:Entity {thread_id: $subject_id}) "
            "RETURN e.type AS type, e.value AS value, e.notes AS notes "
            "ORDER BY type, value LIMIT $limit",
            subject_id=_sanitize_thread_id(subject_id), limit=limit,
        )
        for record in entities:
            note = f" — {record['notes']}" if record["notes"] else ""
            lines.append(f"ENTITY | {record['type']} | {record['value']}{note}")

        evidence = session.run(
            "MATCH (e:Evidence {subject_id: $subject_id}) "
            "WHERE e.status = 'confirmed' "
            "RETURN e.claim AS claim, e.source_url AS source_url, e.source_title AS source_title "
            "ORDER BY e.created_at DESC LIMIT $limit",
            subject_id=_sanitize_thread_id(subject_id), limit=limit,
        )
        for record in evidence:
            source = record["source_url"] or record["source_title"] or "unknown source"
            lines.append(f"CONFIRMED EVIDENCE | {record['claim']} | source: {source}")

    return "No confirmed subject knowledge is available yet." if not lines else "\n".join(lines)


def list_subject_evidence(subject_id: str, status: str | None = None) -> list[dict[str, Any]]:
    driver = get_neo4j_driver()
    query = (
        "MATCH (e:Evidence {subject_id: $subject_id}) "
        + ("WHERE e.status = $status " if status else "")
        + "RETURN e.evidence_id AS evidence_id, e.kind AS kind, e.entity_type AS entity_type, "
          "e.entity_value AS entity_value, e.metadata_key AS metadata_key, "
          "e.proposed_value AS proposed_value, e.claim AS claim, e.source_url AS source_url, "
          "e.source_title AS source_title, e.confidence AS confidence, e.status AS status, "
          "e.thread_id AS thread_id, e.created_at AS created_at ORDER BY e.created_at DESC"
    )
    with driver.session() as session:
        result = session.run(query, subject_id=_sanitize_thread_id(subject_id), status=status)
        return [dict(record) for record in result]


def update_subject_evidence(subject_id: str, evidence_id: str, updates: dict[str, Any]) -> dict | None:
    allowed = {k: v for k, v in updates.items() if k in {"status", "claim", "confidence"}}
    if not allowed:
        return None
    driver = get_neo4j_driver()
    safe_subject_id = _sanitize_thread_id(subject_id)
    with driver.session() as session:
        record = session.run(
            "MATCH (e:Evidence {subject_id: $subject_id, evidence_id: $evidence_id}) "
            "OPTIONAL MATCH (e)-[:SUPPORTS]->(entity:Entity) "
            "WITH e, collect(entity)[0] AS entity "
            "SET e += $updates "
            "RETURN e.evidence_id AS evidence_id, e.kind AS kind, e.entity_type AS entity_type, "
            "e.entity_value AS entity_value, e.metadata_key AS metadata_key, "
            "e.proposed_value AS proposed_value, e.claim AS claim, e.source_url AS source_url, "
            "e.source_title AS source_title, e.confidence AS confidence, e.status AS status, "
            "e.thread_id AS thread_id, e.created_at AS created_at, entity.metadata_json AS metadata_json, "
            "entity.type AS linked_entity_type, entity.value AS linked_entity_value",
            subject_id=safe_subject_id, evidence_id=evidence_id, updates=allowed,
        ).single()
        if not record:
            return None

        result = dict(record)
        if result.get("kind") == "entity_metadata" and allowed.get("status") == "confirmed":
            entity_type = result.get("linked_entity_type") or result.get("entity_type")
            entity_value = result.get("linked_entity_value") or result.get("entity_value")
            metadata_key = result.get("metadata_key")
            proposed_value = result.get("proposed_value")
            if entity_type and entity_value and metadata_key and proposed_value is not None:
                try:
                    metadata = json.loads(result.get("metadata_json") or "{}")
                    if not isinstance(metadata, dict):
                        metadata = {}
                except (TypeError, json.JSONDecodeError):
                    metadata = {}
                try:
                    value = json.loads(proposed_value)
                except (TypeError, json.JSONDecodeError):
                    value = proposed_value
                entries = metadata.get(metadata_key, [])
                if not isinstance(entries, list):
                    entries = [entries]
                if not any(isinstance(entry, dict) and entry.get("value") == value for entry in entries):
                    entries.append({"value": value, "evidence_ids": [evidence_id]})
                else:
                    for entry in entries:
                        if isinstance(entry, dict) and entry.get("value") == value:
                            entry.setdefault("evidence_ids", [])
                            if evidence_id not in entry["evidence_ids"]:
                                entry["evidence_ids"].append(evidence_id)
                metadata[metadata_key] = entries
                session.run(
                    "MATCH (entity:Entity {thread_id: $subject_id, type: $entity_type, value: $entity_value}) "
                    "SET entity.metadata_json = $metadata_json, entity.metadata_updated_at = timestamp()",
                    subject_id=safe_subject_id, entity_type=entity_type, entity_value=entity_value,
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                )
                result["metadata_json"] = json.dumps(metadata, ensure_ascii=False)

        result.pop("metadata_json", None)
        result.pop("linked_entity_type", None)
        result.pop("linked_entity_value", None)
        return result


def migrate_thread_knowledge_to_subject(
    thread_id: str,
    subject_id: str,
    evidence_records: list[dict[str, str]] | None = None,
) -> dict[str, int]:
    """Copy thread-scoped graph findings into a subject namespace.

    Older threads may have been investigated before a subject was attached.
    Their entities and relationships are valid findings, but are namespaced by
    thread. This migration keeps the original graph intact and creates
    pending subject evidence from the saved knowledge-agent calls.
    """
    source_id = _sanitize_thread_id(thread_id)
    target_id = _sanitize_thread_id(subject_id)
    if source_id == target_id:
        return {"entities": 0, "edges": 0, "evidence": 0}

    driver = get_neo4j_driver()
    entity_rows: list[dict[str, Any]] = []
    edge_rows: list[dict[str, str]] = []
    with driver.session() as session:
        result = session.run(
            "MATCH (e:Entity {thread_id: $thread_id}) "
            "RETURN e.type AS type, e.value AS value, e.notes AS notes, e.metadata_json AS metadata_json",
            thread_id=source_id,
        )
        entity_rows = [
            {
                "type": str(row["type"] or "other"),
                "value": str(row["value"] or ""),
                "notes": str(row["notes"] or ""),
                "metadata_json": str(row["metadata_json"] or ""),
            }
            for row in result
            if row["value"]
        ]
        result = session.run(
            "MATCH (a:Entity {thread_id: $thread_id})-[r]->(b:Entity {thread_id: $thread_id}) "
            "RETURN a.type AS from_type, a.value AS from_value, type(r) AS relation_type, "
            "b.type AS to_type, b.value AS to_value, r.notes AS notes",
            thread_id=source_id,
        )
        edge_rows = [
            {
                "from_type": str(row["from_type"] or "other"),
                "from_value": str(row["from_value"] or ""),
                "relation_type": str(row["relation_type"] or "MENTIONS"),
                "to_type": str(row["to_type"] or "other"),
                "to_value": str(row["to_value"] or ""),
                "notes": str(row["notes"] or ""),
            }
            for row in result
            if row["from_value"] and row["to_value"]
        ]

        for entity in entity_rows:
            label = _sanitize_label(entity["type"])
            session.run(
                f"MERGE (e:Entity {{thread_id: $thread_id, type: $type, value: $value}}) "
                f"ON CREATE SET e.notes = $notes, e.metadata_json = CASE WHEN $metadata_json = '' THEN e.metadata_json ELSE $metadata_json END, e.created_at = timestamp() "
                f"ON MATCH SET e.notes = CASE WHEN $notes = '' THEN e.notes "
                f"WHEN e.notes IS NULL OR e.notes = '' THEN $notes "
                f"WHEN NOT e.notes CONTAINS $notes THEN e.notes + ' | ' + $notes ELSE e.notes END "
                f"SET e:{label}",
                thread_id=target_id, type=entity["type"], value=entity["value"], notes=entity["notes"], metadata_json=entity["metadata_json"],
            )

        for edge in edge_rows:
            relation_type = _sanitize_relationship_type(edge["relation_type"])
            session.run(
                f"MATCH (a:Entity {{thread_id: $thread_id, type: $from_type, value: $from_value}}) "
                f"MATCH (b:Entity {{thread_id: $thread_id, type: $to_type, value: $to_value}}) "
                f"MERGE (a)-[r:{relation_type} {{thread_id: $thread_id}}]->(b) "
                f"ON CREATE SET r.notes = $notes, r.created_at = timestamp() "
                f"ON MATCH SET r.notes = CASE WHEN $notes = '' THEN r.notes "
                f"WHEN r.notes IS NULL OR r.notes = '' THEN $notes "
                f"WHEN NOT r.notes CONTAINS $notes THEN r.notes + ' | ' + $notes ELSE r.notes END",
                thread_id=target_id, from_type=edge["from_type"], from_value=edge["from_value"],
                to_type=edge["to_type"], to_value=edge["to_value"], notes=edge["notes"],
            )

        evidence_count = 0
        for record in evidence_records or []:
            claim = str(record.get("claim", "") or "").strip()
            if not claim:
                continue
            source_url = str(record.get("source_url", "") or "")
            source_title = str(record.get("source_title", "") or "")
            evidence_id = "EVD-" + hashlib.sha256(
                f"{target_id}|{source_id}|{source_url}|{source_title}|{claim}".encode("utf-8")
            ).hexdigest()[:12].upper()
            session.run(
                "MERGE (ev:Evidence {evidence_id: $evidence_id}) "
                "ON CREATE SET ev.subject_id = $subject_id, ev.thread_id = $thread_id, "
                "ev.claim = $claim, ev.source_url = $source_url, ev.source_title = $source_title, "
                "ev.confidence = 0.5, ev.status = 'pending', ev.created_at = timestamp()",
                evidence_id=evidence_id, subject_id=target_id, thread_id=source_id,
                claim=claim[:12000], source_url=source_url, source_title=source_title,
            )
            session.run(
                "MATCH (ev:Evidence {evidence_id: $evidence_id}) "
                "MATCH (e:Entity {thread_id: $thread_id}) "
                "WHERE e.value IN $values "
                "MERGE (ev)-[:SUPPORTS]->(e)",
                evidence_id=evidence_id, thread_id=target_id,
                values=[entity["value"] for entity in entity_rows],
            )
            evidence_count += 1

    _mirror_entities_to_file(target_id)
    _mirror_relations_to_file(target_id)
    return {"entities": len(entity_rows), "edges": len(edge_rows), "evidence": evidence_count}
