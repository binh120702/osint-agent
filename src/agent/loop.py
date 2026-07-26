"""
Custom agent loop — replaces LangGraph StateGraph.

The loop:
  1. Prepend system prompt to the current message history
  2. Call LLM (with tools bound)
  3. If the LLM wants to call tools → execute them, append results, loop
  4. If the LLM returns plain text → yield final AIMessage and stop

Thread state (message history) is stored in-memory keyed by thread_id.
"""
from __future__ import annotations

import json
import os
import uuid
import queue
import threading
import logging
from typing import Callable, Iterator

logger = logging.getLogger("agent.loop")

from agent.messages import (
    AnyMessage,
    AIMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from llms.client_factory import ACTIVE_LLM_CLIENT
from prompts import MAIN_PROMPT
from tools.all_tools import get_all_tools
from tools.knowledge_base import set_kb_thread_id


_MAX_TOOL_CHARS = int(os.getenv("OSINT_MAX_TOOL_CHARS", "8000"))
_MAX_ITERATIONS = 50  # safety cap to avoid infinite loops

# In-memory thread store: thread_id → list of messages (no system prompt stored)
_THREADS: dict[str, list[AnyMessage]] = {}

# Cached tool list (refreshed on each turn to pick up tool_config.json changes)
_CACHED_TOOLS: list = []
_CACHED_TOOL_SCHEMAS: list[dict] = []
_TOOLS_BY_NAME: dict[str, object] = {}


def _refresh_tools() -> None:
    global _CACHED_TOOLS, _CACHED_TOOL_SCHEMAS, _TOOLS_BY_NAME
    tools = get_all_tools()
    _CACHED_TOOLS = tools
    _CACHED_TOOL_SCHEMAS = [t.schema for t in tools]
    _TOOLS_BY_NAME = {t.name: t for t in tools}


def _truncate(text: str) -> str:
    if len(text) <= _MAX_TOOL_CHARS:
        return text
    suffix = "\n\n[tool output truncated to avoid context overflow]"
    keep = _MAX_TOOL_CHARS - len(suffix)
    return text[:max(keep, 0)] + suffix


from pathlib import Path
import json

_DATA_DIR = Path(__file__).parent.parent / "data" / "threads"


def save_thread(thread_id: str) -> None:
    """Save thread history to disk."""
    if thread_id not in _THREADS:
        return
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _DATA_DIR / f"{thread_id}.json"
    data = [m.to_dict() for m in _THREADS[thread_id]]
    file_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def get_thread(thread_id: str) -> list[AnyMessage]:
    """Return the message history for a thread (creates it if new, loads from disk if exists)."""
    if thread_id in _THREADS:
        return _THREADS[thread_id]

    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _DATA_DIR / f"{thread_id}.json"
    if file_path.exists():
        try:
            from agent.messages import from_dict
            data = json.loads(file_path.read_text(encoding="utf-8"))
            msgs = [from_dict(m) for m in data]
            _THREADS[thread_id] = msgs
            return msgs
        except Exception:
            pass

    msgs = []
    _THREADS[thread_id] = msgs
    return msgs


def list_threads() -> list[dict]:
    """Return a summary list of all active threads from memory and disk, sorted by modification time."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    thread_ids = set(_THREADS.keys())
    for f in _DATA_DIR.glob("*.json"):
        thread_ids.add(f.stem)

    result = []
    for tid in thread_ids:
        msgs = get_thread(tid)
        title = ""
        for m in msgs:
            if isinstance(m, HumanMessage):
                title = m.content[:80]
                break
        
        fpath = _DATA_DIR / f"{tid}.json"
        mtime = os.path.getmtime(fpath) if fpath.exists() else 0.0
        
        result.append({
            "thread_id": tid,
            "message_count": len(msgs),
            "title": title,
            "mtime": mtime
        })
        
    result.sort(key=lambda x: x["mtime"], reverse=True)
    for item in result:
        del item["mtime"]
        
    return result


def delete_thread(thread_id: str) -> bool:
    deleted = False
    if thread_id in _THREADS:
        del _THREADS[thread_id]
        deleted = True
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    file_path = _DATA_DIR / f"{thread_id}.json"
    if file_path.exists():
        try:
            file_path.unlink()
            deleted = True
        except Exception:
            pass
    return deleted


def run(
    thread_id: str,
    user_message: str,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_end: Callable[[str, str], None] | None = None,
    llm_client: LLMClient | None = None,
) -> Iterator[str]:
    """
    Run one user turn of the agent loop.

    Yields:
        str chunks of the final LLM text response (streamed).

    Side effects:
        - Appends HumanMessage to thread history
        - Appends AIMessage and ToolMessages to thread history
    """
    _refresh_tools()
    set_kb_thread_id(thread_id)

    client = llm_client or ACTIVE_LLM_CLIENT
    history = get_thread(thread_id)
    history.append(HumanMessage(content=user_message))
    save_thread(thread_id)
    logger.info("Starting run for thread_id=%s. LLM client provider=%s, model=%s", thread_id, getattr(client, "provider", "unknown"), getattr(client, "model", "unknown"))

    for _iteration in range(_MAX_ITERATIONS):
        logger.info("Iteration %d/%d: Calling LLM...", _iteration + 1, _MAX_ITERATIONS)
        # Build full message list for LLM: system + history
        full_messages: list[AnyMessage] = [SystemMessage(content=MAIN_PROMPT)] + history

        # Call LLM (non-streaming first to handle tool calls)
        ai_msg = client.invoke(full_messages, tools=_CACHED_TOOL_SCHEMAS)
        history.append(ai_msg)
        save_thread(thread_id)

        if not ai_msg.tool_calls:
            logger.info("No tool calls. Yielding final response (length=%d).", len(ai_msg.content or ""))
            if ai_msg.content:
                yield ai_msg.content
            return

        logger.info("LLM requested %d tool call(s)", len(ai_msg.tool_calls))
        # Execute each tool call
        for tc in ai_msg.tool_calls:
            logger.info("⚡ Executing tool: '%s' with arguments: %s", tc.name, json.dumps(tc.arguments, ensure_ascii=False))
            tool_fn = _TOOLS_BY_NAME.get(tc.name)

            if on_tool_start:
                on_tool_start(tc.name, tc.arguments)

            if tool_fn is None:
                result = f"Error: tool '{tc.name}' not found."
                logger.error("Tool '%s' not found.", tc.name)
            else:
                try:
                    set_kb_thread_id(thread_id)
                    result = tool_fn.invoke(tc.arguments)
                    if not isinstance(result, str):
                        result = json.dumps(result, default=str)
                    result = _truncate(result)
                    logger.info("⚙️ Tool '%s' execution complete. Result preview: %s", tc.name, result[:200] + ("..." if len(result) > 200 else ""))
                except Exception as exc:
                    result = f"Tool '{tc.name}' raised an error: {exc}"
                    logger.exception("Error executing tool '%s': %s", tc.name, exc)

            if on_tool_end:
                on_tool_end(tc.name, result)

            history.append(ToolMessage(content=result, tool_call_id=tc.id))
            save_thread(thread_id)

    # Exceeded max iterations
    logger.warning("Agent loop exceeded max iterations (%d).", _MAX_ITERATIONS)
    yield "[Agent loop exceeded max iterations without a final answer.]"


def run_streaming(
    thread_id: str,
    user_message: str,
    on_tool_start: Callable[[str, dict], None] | None = None,
    on_tool_end: Callable[[str, str], None] | None = None,
    llm_client: LLMClient | None = None,
) -> Iterator[str]:
    """
    Same as run() but yields SSE-formatted event strings for the FastAPI endpoint.

    Event types:
        data: {"type": "text", "chunk": "..."}
        data: {"type": "tool_start", "name": "...", "args": {...}}
        data: {"type": "tool_end", "name": "...", "result": "..."}
        data: {"type": "done"}
        data: {"type": "error", "message": "..."}
    """
    import time

    def _event(payload: dict) -> str:
        return f"data: {json.dumps(payload)}\n\n"

    def _on_tool_start(name: str, args: dict) -> None:
        pass  # handled inline below

    def _on_tool_end(name: str, result: str) -> None:
        pass  # handled inline below

    _refresh_tools()
    set_kb_thread_id(thread_id)

    client = llm_client or ACTIVE_LLM_CLIENT
    history = get_thread(thread_id)
    history.append(HumanMessage(content=user_message))
    save_thread(thread_id)
    logger.info("Starting run_streaming for thread_id=%s. LLM client provider=%s, model=%s", thread_id, getattr(client, "provider", "unknown"), getattr(client, "model", "unknown"))

    start_time = time.time()
    tool_call_count = 0
    iteration_count = 0

    try:
        for _iteration in range(_MAX_ITERATIONS):
            iteration_count += 1
            logger.info("Iteration %d/%d: Calling LLM...", iteration_count, _MAX_ITERATIONS)
            full_messages: list[AnyMessage] = [SystemMessage(content=MAIN_PROMPT)] + history

            q = queue.Queue()
            ai_msg_container = []
            exception_container = []

            def target():
                try:
                    msg = client.invoke_streaming(
                        full_messages,
                        tools=_CACHED_TOOL_SCHEMAS,
                        chunk_queue=q
                    )
                    ai_msg_container.append(msg)
                except Exception as exc:
                    exception_container.append(exc)
                    q.put(None)

            thread = threading.Thread(target=target)
            thread.start()

            while True:
                chunk = q.get()
                if chunk is None:
                    break
                yield _event({"type": "text", "chunk": chunk})

            thread.join()

            if exception_container:
                logger.error("LLM streaming call failed: %s", exception_container[0])
                raise exception_container[0]

            ai_msg = ai_msg_container[0]
            history.append(ai_msg)
            save_thread(thread_id)

            if not ai_msg.tool_calls:
                duration = round(time.time() - start_time, 2)
                logger.info("No tool calls. Final answer complete (duration=%s sec, iterations=%d, tools_called=%d).", duration, iteration_count, tool_call_count)
                yield _event({
                    "type": "done",
                    "metrics": {
                        "duration_sec": duration,
                        "iterations": iteration_count,
                        "tools_called": tool_call_count,
                    }
                })
                return

            logger.info("LLM requested %d tool call(s)", len(ai_msg.tool_calls))
            for tc in ai_msg.tool_calls:
                tool_call_count += 1
                logger.info("⚡ Executing tool: '%s' with arguments: %s", tc.name, json.dumps(tc.arguments, ensure_ascii=False))
                yield _event({"type": "tool_start", "name": tc.name, "args": tc.arguments})

                tool_fn = _TOOLS_BY_NAME.get(tc.name)
                if tool_fn is None:
                    result = f"Error: tool '{tc.name}' not found."
                    logger.error("Tool '%s' not found.", tc.name)
                else:
                    try:
                        set_kb_thread_id(thread_id)
                        result = tool_fn.invoke(tc.arguments)
                        if not isinstance(result, str):
                            result = json.dumps(result, default=str)
                        result = _truncate(result)
                        logger.info("⚙️ Tool '%s' execution complete. Result preview: %s", tc.name, result[:200] + ("..." if len(result) > 200 else ""))
                    except Exception as exc:
                        result = f"Tool '{tc.name}' raised an error: {exc}"
                        logger.exception("Error executing tool '%s': %s", tc.name, exc)

                yield _event({"type": "tool_end", "name": tc.name, "result": result[:500]})
                history.append(ToolMessage(content=result, tool_call_id=tc.id))
                save_thread(thread_id)

        logger.warning("Agent loop exceeded max iterations (%d).", _MAX_ITERATIONS)
        yield _event({"type": "error", "message": "Agent loop exceeded max iterations."})

    except Exception as exc:
        logger.exception("Exception in run_streaming: %s", exc)
        yield _event({"type": "error", "message": str(exc)})
