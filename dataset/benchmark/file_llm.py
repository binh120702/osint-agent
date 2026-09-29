"""File-backed LLM client for bounded host-side benchmark inference."""
from __future__ import annotations

import json
import os
import queue
import time
from pathlib import Path
from typing import Iterator

from agent.messages import AIMessage, AnyMessage, ToolCall
from llms.llm_client import LLMClient


def _messages_to_openai(messages: list[AnyMessage]) -> list[dict]:
    result: list[dict] = []
    for message in messages:
        item = message.to_dict()
        for tool_call in item.get("tool_calls", []):
            arguments = tool_call.get("function", {}).get("arguments")
            if isinstance(arguments, dict):
                tool_call["function"]["arguments"] = json.dumps(arguments, ensure_ascii=False)
        result.append(item)
    return result


def _parse_tool_calls(raw_tool_calls) -> list[ToolCall]:
    parsed: list[ToolCall] = []
    for index, call in enumerate(raw_tool_calls or []):
        function = call.get("function", {}) if isinstance(call, dict) else {}
        arguments = function.get("arguments", "{}")
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments or "{}")
            except json.JSONDecodeError:
                arguments = {}
        parsed.append(
            ToolCall(
                id=str(call.get("id", f"bridge-call-{index}")),
                name=str(function.get("name", "")),
                arguments=arguments if isinstance(arguments, dict) else {},
            )
        )
    return parsed


class FileBridgeLLMClient(LLMClient):
    """LLM client that exchanges requests and responses through JSON files."""

    provider = "file-bridge"

    def __init__(self, io: str | Path, model_name: str | None = None, max_requests: int | None = None):
        self.io = Path(io)
        self.io.mkdir(parents=True, exist_ok=True)
        self.max_requests = max_requests or int(os.environ.get("BENCHMARK_MAX_REQUESTS", "80"))
        self.response_timeout = int(os.environ.get("BENCHMARK_RESPONSE_TIMEOUT", "900"))
        self.count = 0
        super().__init__(model_name or os.environ.get("BENCHMARK_MODEL", os.environ.get("OPENAI_MODEL_ID", "gpt-4o")))

    def _request(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> dict:
        self.count += 1
        if self.count > self.max_requests:
            raise RuntimeError("benchmark LLM request budget exhausted")
        request_path = self.io / f"request-{self.count:04d}.json"
        payload = {
            "model": self.model_name,
            "messages": _messages_to_openai(messages),
            "temperature": 0,
        }
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        response_path = self.io / f"response-{self.count:04d}.json"
        deadline = time.monotonic() + self.response_timeout
        while not response_path.exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("host inference bridge response timeout")
            time.sleep(0.1)
        response = json.loads(response_path.read_text(encoding="utf-8"))
        if "bridge_error" in response:
            raise RuntimeError(str(response["bridge_error"]))
        try:
            return response["choices"][0]["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("file bridge returned an invalid response payload") from exc

    def invoke(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> AIMessage:
        raw = self._request(messages, tools)
        return AIMessage(content=str(raw.get("content") or ""), tool_calls=_parse_tool_calls(raw.get("tool_calls")))

    def invoke_streaming(
        self,
        messages: list[AnyMessage],
        tools: list[dict] | None = None,
        chunk_queue: queue.Queue | None = None,
    ) -> AIMessage:
        message = self.invoke(messages, tools)
        if chunk_queue is not None:
            if message.content:
                chunk_queue.put(message.content)
            chunk_queue.put(None)
        return message

    def stream(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> Iterator[str]:
        message = self.invoke(messages, tools)
        if message.content:
            yield message.content

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        raise RuntimeError("FileBridgeLLMClient does not support image descriptions")
