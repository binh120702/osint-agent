"""Recorded LLM client for deterministic benchmark regression runs.

The fixture is a JSON array of assistant turns. Each item is either:
{"content": "...", "tool_calls": [{"name": "tool", "arguments": {...}}]}
(or an OpenAI-like tool-call object). The client fails when the agent asks for
more turns than the fixture contains, preventing accidental live API use.
"""
from __future__ import annotations

import json
import queue
from pathlib import Path
from typing import Iterator

from agent.messages import AIMessage, AnyMessage, ToolCall
from llms.llm_client import LLMClient


class RecordedLLMClient(LLMClient):
    provider = "recorded"

    def __init__(self, fixture: str | Path):
        self.fixture = Path(fixture)
        raw = json.loads(self.fixture.read_text(encoding="utf-8"))
        if not isinstance(raw, list):
            raise ValueError("Recorded LLM fixture must be a JSON array")
        self.turns = raw
        self.position = 0
        super().__init__(model_name=f"recorded:{self.fixture.name}")

    def _next(self) -> AIMessage:
        if self.position >= len(self.turns):
            raise RuntimeError(f"Recorded LLM fixture exhausted: {self.fixture}")
        item = self.turns[self.position]
        self.position += 1
        if not isinstance(item, dict):
            raise ValueError(f"Fixture turn {self.position} must be an object")
        calls = []
        for index, call in enumerate(item.get("tool_calls", [])):
            function = call.get("function", call)
            args = function.get("arguments", {})
            if isinstance(args, str):
                args = json.loads(args)
            calls.append(ToolCall(id=call.get("id", f"recorded-{self.position}-{index}"),
                                  name=function["name"], arguments=args))
        return AIMessage(content=str(item.get("content", "")), tool_calls=calls)

    def invoke(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> AIMessage:
        return self._next()

    def invoke_streaming(self, messages: list[AnyMessage], tools: list[dict] | None = None,
                         chunk_queue: queue.Queue | None = None) -> AIMessage:
        message = self._next()
        if chunk_queue is not None:
            if message.content:
                chunk_queue.put(message.content)
            chunk_queue.put(None)
        return message

    def stream(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> Iterator[str]:
        message = self._next()
        if message.content:
            yield message.content

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        raise RuntimeError("RecordedLLMClient cannot describe images")
