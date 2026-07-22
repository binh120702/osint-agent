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


# ── Request / response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None  # if None, a new thread is created


class ToggleToolRequest(BaseModel):
    enabled: bool


# ── Chat endpoint ────────────────────────────────────────────────────────────

@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Send a user message; stream back SSE events."""
    thread_id = req.thread_id or str(uuid.uuid4())

    def generate():
        # First emit the thread_id so the UI can save it
        yield f"data: {json.dumps({'type': 'thread_id', 'thread_id': thread_id})}\n\n"
        yield from agent_loop.run_streaming(thread_id, req.message)

    return StreamingResponse(generate(), media_type="text/event-stream")


# ── Thread management ────────────────────────────────────────────────────────

@app.get("/api/threads")
def list_threads():
    return agent_loop.list_threads()


@app.get("/api/threads/{thread_id}/messages")
def get_messages(thread_id: str):
    history = agent_loop.get_thread(thread_id)
    result = []
    for m in history:
        d = m.to_dict()
        # Simplify tool_calls to avoid heavy payload
        if "tool_calls" in d and d["tool_calls"]:
            d["tool_calls"] = [
                {"name": tc["function"]["name"]} for tc in d["tool_calls"]
            ]
        result.append(d)
    return result


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
        from tools.knowledge_base import kb_get, set_kb_thread_id
        set_kb_thread_id(thread_id)
        result = kb_get.invoke({})
        return json.loads(result) if isinstance(result, str) else result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/kb/{thread_id}/edges")
def kb_edges(thread_id: str):
    try:
        from tools.knowledge_base import kb_get_edges, set_kb_thread_id
        set_kb_thread_id(thread_id)
        result = kb_get_edges.invoke({})
        return json.loads(result) if isinstance(result, str) else result
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Static UI ────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def serve_ui():
    index = STATIC_DIR / "index.html"
    if not index.exists():
        return HTMLResponse("<h1>UI not found. Place index.html in src/static/</h1>", status_code=404)
    return HTMLResponse(index.read_text(encoding="utf-8"))
