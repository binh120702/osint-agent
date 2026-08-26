"""
OSINT Agent — FastAPI server.

Endpoints:
  POST   /api/chat                         — send a message, stream SSE response
  GET    /api/threads                       — list active threads
  GET    /api/threads/{thread_id}/messages  — get full message history
  DELETE /api/threads/{thread_id}           — delete a thread
  GET    /api/tools                         — list enabled tools
  POST   /api/tools/{name}/toggle          — enable/disable a tool
  GET    /api/kb/{thread_id}/entities       — KB entities
  GET    /api/kb/{thread_id}/edges          — KB graph edges
  GET    /                                  — serve the chat UI
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent import loop as agent_loop
from agent.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from tools.all_tools import get_all_tools, _load_tool_config
from tools.knowledge_base import (
    get_neo4j_driver,
    list_subject_evidence,
    migrate_thread_knowledge_to_subject,
    update_subject_evidence,
)
from subject_manager import get_subject_manager
from models.subject import (
    SubjectCreateRequest,
    SubjectUpdateRequest,
    EvidenceUpdateRequest,
    EvidenceStatus,
)

import os

app = FastAPI(title="OSINT Agent API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

STATIC_DIR = Path(__file__).parent / "static"
FRONTEND_DIST_DIR = Path(__file__).parent.parent / "frontend" / "dist"


def _decode_entity_metadata(raw: object) -> dict:
    """Decode the JSON string used for structured Neo4j entity metadata."""
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(str(raw))
        return value if isinstance(value, dict) else {}
    except (TypeError, json.JSONDecodeError):
        return {}

if FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")


# ── Request / response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # if None, a new thread is created
    subject_id: str | None = None
    provider: str | None = None
    model_name: str | None = None


class ToggleToolRequest(BaseModel):
    enabled: bool


class SubjectDraftRequest(BaseModel):
    provider: str | None = None
    model_name: str | None = None


class ThreadSubjectAttachRequest(SubjectCreateRequest):
    pass


# ── Chat endpoint ────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Send a user message; stream back SSE events."""
    thread_id = req.thread_id or str(uuid.uuid4())
    manager = get_subject_manager()
    subject_id = req.subject_id
    if not subject_id and req.thread_id:
        linked = manager.get_by_thread(req.thread_id)
        subject_id = linked.subject_id if linked else None
    if subject_id and not manager.get(subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    if subject_id and not req.thread_id:
        manager.add_thread(subject_id, thread_id)

    llm_client = None
    if req.provider or req.model_name:
        try:
            from llms.client_factory import get_llm_client_for
            llm_client = get_llm_client_for(req.provider, req.model_name)
        except Exception as e:
            def err_generator():
                yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
            return StreamingResponse(err_generator(), media_type="text/event-stream")

    def generate():
        # First emit the thread_id so the UI can save it
        yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread_id})}\n\n"
        yield from agent_loop.run_streaming(
            thread_id, req.message, subject_id=subject_id, llm_client=llm_client
        )

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Thread management ────────────────────────────────────────────────────────

@app.get("/api/threads")
def list_threads():
    subjects = get_subject_manager()
    result = agent_loop.list_threads()
    for thread in result:
        subject = subjects.get_by_thread(thread["thread_id"])
        thread["subject_id"] = subject.subject_id if subject else None
        thread["subject_name"] = subject.name if subject else None
    return result


@app.get("/api/threads/{thread_id}/messages")
def get_messages(thread_id: str):
    history = agent_loop.get_thread(thread_id)
    ui_messages = []
    
    # Pre-map tool_call_id -> {name, arguments} from assistant messages
    tool_calls_map = {}
    for m in history:
        d = m.to_dict()
        if d.get("role") == "assistant" and d.get("tool_calls"):
            for tc in d["tool_calls"]:
                tc_id = tc.get("id")
                func = tc.get("function", {})
                name = func.get("name")
                args = func.get("arguments", {})
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                tool_calls_map[tc_id] = {"name": name, "args": args}
                
    for m in history:
        d = m.to_dict()
        role = d.get("role")
        
        if role == "user":
            ui_messages.append({
                "role": "user",
                "content": d.get("content", "")
            })
        elif role == "assistant":
            content = d.get("content", "")
            metrics = d.get("metrics")
            if content and content.strip():
                ui_messages.append({
                    "role": "assistant",
                    "content": content,
                    "metrics": metrics
                })
        elif role == "tool":
            tc_id = d.get("tool_call_id")
            tc_info = tool_calls_map.get(tc_id, {})
            name = tc_info.get("name", d.get("name") or "tool")
            args = tc_info.get("args")
            
            ui_messages.append({
                "role": "tool",
                "content": "",
                "isToolCall": True,
                "toolName": name,
                "toolArgs": args,
                "toolResult": d.get("content", "")
            })
            
    return ui_messages


@app.delete("/api/threads/{thread_id}")
def delete_thread(thread_id: str):
    deleted = agent_loop.delete_thread(thread_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Thread not found")
    return {"deleted": thread_id}


@app.post("/api/threads")
def create_unassigned_thread():
    """Create a persisted thread before a subject has been selected."""
    thread_id = str(uuid.uuid4())
    agent_loop.get_thread(thread_id)
    agent_loop.save_thread(thread_id)
    return {"thread_id": thread_id, "subject_id": None}


@app.post("/api/threads/{thread_id}/subject-draft")
def create_subject_draft(thread_id: str, request: SubjectDraftRequest):
    """Use the selected model to propose subject metadata from thread history."""
    history = agent_loop.get_thread(thread_id)
    transcript_parts = []
    for message in history:
        if message.role not in {"user", "assistant"}:
            continue
        content = message.content.strip()
        if content:
            transcript_parts.append(f"{message.role.upper()}: {content}")
    transcript = "\n\n".join(transcript_parts)
    if not transcript:
        raise HTTPException(status_code=400, detail="The thread has no conversation history yet")

    prompt = """You extract an investigation subject from a research conversation.
Return only valid JSON with exactly these fields:
name (string), subject_type (one of person, company, organization, domain, account, location, event, other),
canonical_identifier (string or null), aliases (array of strings), identifiers (array of strings),
description (string), investigation_goals (string).

Use only information supported by the conversation. If a field is unknown, use null for canonical_identifier and [] for arrays. Do not invent a real identity. Keep the description and goals concise."""

    try:
        from llms.client_factory import get_llm_client_for
        from agent.messages import HumanMessage, SystemMessage

        client = get_llm_client_for(request.provider, request.model_name)
        result = client.invoke([
            SystemMessage(content=prompt),
            HumanMessage(content=transcript[-16000:]),
        ])
        raw = (result.content or "").strip()
        if raw.startswith("```"):
            raw = raw.strip("`").removeprefix("json").strip()
        start = raw.find("{")
        end = raw.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The model did not return a JSON subject draft")
        draft = json.loads(raw[start:end + 1])
        validated = SubjectCreateRequest(**draft)
        return validated.dict()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Unable to generate subject draft: {exc}")


@app.post("/api/threads/{thread_id}/subject")
def create_subject_for_thread(thread_id: str, request: ThreadSubjectAttachRequest):
    manager = get_subject_manager()
    if manager.get_by_thread(thread_id):
        raise HTTPException(status_code=409, detail="Thread is already linked to a subject")
    subject = manager.create(request)
    manager.add_thread(subject.subject_id, thread_id)
    migration = migrate_thread_knowledge_to_subject(
        thread_id,
        subject.subject_id,
        _knowledge_agent_evidence_records(thread_id),
    )
    return {**subject.dict(), "migration": migration}


def _knowledge_agent_evidence_records(thread_id: str) -> list[dict[str, str]]:
    """Extract source claims from saved knowledge-agent calls for subject migration."""
    evidence_records = []
    for message in agent_loop.get_thread(thread_id):
        for tool_call in (getattr(message, "tool_calls", None) or []):
            if getattr(tool_call, "name", "") != "knowledge_agent":
                continue
            arguments = getattr(tool_call, "arguments", {}) or {}
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    continue
            if not isinstance(arguments, dict):
                continue
            evidence_records.append({
                "claim": str(arguments.get("text", "")),
                "source_url": str(arguments.get("source_url", "")),
                "source_title": str(arguments.get("source_title", "")),
            })
    return evidence_records


@app.post("/api/threads/{thread_id}/subjects/{subject_id}")
def attach_existing_subject_to_thread(thread_id: str, subject_id: str):
    """Attach an existing subject to an unassigned thread."""
    manager = get_subject_manager()
    subject = manager.get(subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    if not any(item["thread_id"] == thread_id for item in agent_loop.list_threads()):
        raise HTTPException(status_code=404, detail="Thread not found")

    linked = manager.get_by_thread(thread_id)
    if linked and linked.subject_id != subject_id:
        raise HTTPException(status_code=409, detail="Thread is already linked to another subject")

    manager.add_thread(subject_id, thread_id)
    migration = migrate_thread_knowledge_to_subject(
        thread_id,
        subject_id,
        _knowledge_agent_evidence_records(thread_id),
    )
    return {"thread_id": thread_id, "subject_id": subject_id, "migration": migration}


# ── Tool management ─────────────────────────────────────────────────────────

@app.get("/api/tools")
def list_tools():
    config = _load_tool_config()
    tools = get_all_tools()
    all_names = list(config.keys())
    enabled_names = {t.name for t in tools}
    return [
        {"name": n, "enabled": n in enabled_names, "description": ""}
        for n in all_names if not n.startswith("_")
    ]


@app.post("/api/tools/{name}/toggle")
def toggle_tool(name: str, req: ToggleToolRequest):
    """Enable or disable a tool by writing to tool_config.json."""
    from pathlib import Path as P
    config_path = P(__file__).parent / "tools" / "tool_config.json"
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    raw[name] = req.enabled
    config_path.write_text(json.dumps(raw, indent=2), encoding="utf-8")
    return {"name": name, "enabled": req.enabled}


# ── Knowledge Base endpoints ─────────────────────────────────────────────────

@app.get("/api/kb/{thread_id}/entities")
def kb_entities(thread_id: str):
    try:
        from tools.knowledge_base import get_neo4j_driver
        driver = get_neo4j_driver()
        query = """
        MATCH (e:Entity {thread_id: $thread_id})
        RETURN labels(e) AS labels, e.type AS type, e.value AS value, e.notes AS notes, e.metadata_json AS metadata_json
        ORDER BY type, value
        """
        entities = []
        with driver.session() as session:
            result = session.run(query, thread_id=thread_id)
            for record in result:
                labels = record["labels"] or []
                label = next((l for l in labels if l != "Entity"), record["type"].upper())
                entities.append({
                    "id": f"{record['type'].lower()}_{record['value']}",
                    "label": label,
                    "properties": {
                        "name": record["value"],
                        "notes": record["notes"] or "",
                        "metadata": _decode_entity_metadata(record["metadata_json"]),
                    }
                })
        return entities
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/kb/{thread_id}/edges")
def kb_edges(thread_id: str):
    try:
        from tools.knowledge_base import get_neo4j_driver
        driver = get_neo4j_driver()
        query = """
        MATCH (from:Entity {thread_id: $thread_id})-[r]->(to:Entity {thread_id: $thread_id})
        RETURN from.value AS source, to.value AS target, type(r) AS type, r.notes AS notes
        ORDER BY source, type, target
        """
        edges = []
        with driver.session() as session:
            result = session.run(query, thread_id=thread_id)
            for record in result:
                edges.append({
                    "source": record["source"],
                    "target": record["target"],
                    "type": record["type"],
                    "properties": {
                        "notes": record["notes"] or ""
                    }
                })
        return edges
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Subject management ──────────────────────────────────────────────────────

@app.post("/api/subjects")
def create_subject(request: SubjectCreateRequest):
    return get_subject_manager().create(request).dict()


@app.get("/api/subjects")
def list_subjects():
    return [subject.dict() for subject in get_subject_manager().list()]


@app.get("/api/subjects/{subject_id}")
def get_subject(subject_id: str):
    subject = get_subject_manager().get(subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject.dict()


@app.put("/api/subjects/{subject_id}")
def update_subject(subject_id: str, request: SubjectUpdateRequest):
    subject = get_subject_manager().update(subject_id, request)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject.dict()


@app.delete("/api/subjects/{subject_id}")
def delete_subject(subject_id: str):
    manager = get_subject_manager()
    if not manager.get(subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    try:
        driver = get_neo4j_driver()
        with driver.session() as session:
            session.run("MATCH (e:Evidence {subject_id: $subject_id}) DETACH DELETE e", subject_id=subject_id)
            session.run("MATCH (e:Entity {thread_id: $subject_id}) DETACH DELETE e", subject_id=subject_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Unable to delete subject knowledge: {exc}")
    manager.delete(subject_id)
    return {"deleted": subject_id}


@app.post("/api/subjects/{subject_id}/threads")
def create_subject_thread(subject_id: str):
    manager = get_subject_manager()
    if not manager.get(subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    thread_id = str(uuid.uuid4())
    # Materialize the empty transcript so it is a real thread immediately,
    # even before the investigator sends the first message.
    agent_loop.get_thread(thread_id)
    agent_loop.save_thread(thread_id)
    manager.add_thread(subject_id, thread_id)
    return {"thread_id": thread_id, "subject_id": subject_id}


@app.get("/api/subjects/{subject_id}/entities")
def subject_entities(subject_id: str):
    if not get_subject_manager().get(subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    try:
        with get_neo4j_driver().session() as session:
            result = session.run(
                "MATCH (e:Entity {thread_id: $subject_id}) "
                "RETURN e.type AS type, e.value AS value, e.notes AS notes, e.metadata_json AS metadata_json ORDER BY type, value",
                subject_id=subject_id,
            )
            return [
                {"id": f"{r['type']}:{r['value']}", "label": r["type"].upper(),
                 "properties": {"name": r["value"], "notes": r["notes"] or "",
                                "metadata": _decode_entity_metadata(r["metadata_json"])} }
                for r in result
            ]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/subjects/{subject_id}/edges")
def subject_edges(subject_id: str):
    if not get_subject_manager().get(subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    try:
        with get_neo4j_driver().session() as session:
            result = session.run(
                "MATCH (a:Entity {thread_id: $subject_id})-[r]->(b:Entity {thread_id: $subject_id}) "
                "RETURN a.value AS source, b.value AS target, type(r) AS type, r.notes AS notes",
                subject_id=subject_id,
            )
            return [{"source": r["source"], "target": r["target"], "type": r["type"],
                     "properties": {"notes": r["notes"] or ""}} for r in result]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/subjects/{subject_id}/evidence")
def subject_evidence(subject_id: str, status: EvidenceStatus | None = None):
    if not get_subject_manager().get(subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    try:
        return list_subject_evidence(subject_id, status.value if status else None)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.patch("/api/subjects/{subject_id}/evidence/{evidence_id}")
def edit_subject_evidence(subject_id: str, evidence_id: str, request: EvidenceUpdateRequest):
    if not get_subject_manager().get(subject_id):
        raise HTTPException(status_code=404, detail="Subject not found")
    updates = request.dict(exclude_unset=True)
    if isinstance(updates.get("status"), EvidenceStatus):
        updates["status"] = updates["status"].value
    try:
        result = update_subject_evidence(subject_id, evidence_id, updates)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    if not result:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return result


# ── Static UI ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    if FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "index.html").exists():
        index = FRONTEND_DIST_DIR / "index.html"
    else:
        index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>UI not found. Build the frontend or place index.html in src/static/</h1>", status_code=404)
    return HTMLResponse(index.read_text(encoding="utf-8"))
