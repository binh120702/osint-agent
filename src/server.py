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

if FRONTEND_DIST_DIR.exists() and (FRONTEND_DIST_DIR / "assets").exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST_DIR / "assets"), name="assets")


# ── Request / response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # if None, a new thread is created
    provider: str | None = None
    model_name: str | None = None


class ToggleToolRequest(BaseModel):
    enabled: bool


# ── Chat endpoint ────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Send a user message; stream back SSE events."""
    thread_id = req.thread_id or str(uuid.uuid4())

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
        yield from agent_loop.run_streaming(thread_id, req.message, llm_client=llm_client)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Thread management ────────────────────────────────────────────────────────

@app.get("/api/threads")
def list_threads():
    return agent_loop.list_threads()


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
        RETURN labels(e) AS labels, e.type AS type, e.value AS value, e.notes AS notes
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
                        "notes": record["notes"] or ""
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
