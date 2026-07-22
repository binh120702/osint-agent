import json
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


@tool
def kb_current_thread_namespace() -> str:
    """Return the currently resolved KB thread namespace (for debugging thread-id wiring)."""
    return _current_thread_id()


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

    normalized_types: List[Dict[str, str]] = []
    seen: set[str] = set()

    for entry in entity_types:
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
        [f"- {t['type']}: {t.get('description', '').strip()}" for t in entity_types if t.get("type")]
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
      "notes": "optional short note with key evidence, context, or timestamps"
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
    thread_id = _current_thread_id()
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


def _edge_key(from_type: str, from_value: str, relation_type: str, to_type: str, to_value: str) -> str:
    return f"{from_type}||{from_value}||{relation_type}||{to_type}||{to_value}"


@tool
def knowledge_agent(text: str) -> str:
    """Analyze investigation findings to extract, resolve, and save structured entities and relationships to the knowledge base.
    
    Args:
        text: Raw observations, notes, or tool outputs to process.
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
    normalized_entities: List[Dict[str, str]] = []
    for entry in entity_types:
        if isinstance(entry, str):
            normalized_entities.append({"type": entry, "description": ""})
        elif isinstance(entry, dict) and entry.get("type"):
            normalized_entities.append(
                {"type": str(entry.get("type", "")).strip(), "description": str(entry.get("description", "")).strip()}
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
    
    thread_id = _current_thread_id()
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
    except json.JSONDecodeError:
        # Fallback: store raw content in Neo4j if it is not valid JSON
        with driver.session() as session:
            session.run(
                "MERGE (e:Entity {thread_id: $thread_id, type: 'RAW', value: $value}) "
                "SET e:Raw, e.notes = $notes, e.created_at = timestamp()",
                thread_id=thread_id, value=content[:200], notes=content
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

        processed_entities.append({
            "type": etype,
            "value": value,
            "notes": notes
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

    # Process Relations
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
    thread_id = _current_thread_id()
    driver = get_neo4j_driver()
    query = """
    MATCH (from:Entity {thread_id: $thread_id})-[r]->(to:Entity {thread_id: $thread_id})
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
