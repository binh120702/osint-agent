"""OpenAI LLM client — direct openai SDK, no langchain."""
from __future__ import annotations

import json
import os
import queue
from typing import Iterator

from dotenv import load_dotenv
from openai import OpenAI

from agent.messages import AnyMessage, AIMessage, ToolCall
from llms.llm_client import LLMClient


load_dotenv()


def _messages_to_openai(messages: list[AnyMessage]) -> list[dict]:
    """Convert our message types to OpenAI-compatible dicts."""
    result = []
    for m in messages:
        d = m.to_dict()
        # OpenAI expects tool_calls.function.arguments as a JSON *string*
        if d.get("tool_calls"):
            for tc in d["tool_calls"]:
                if isinstance(tc["function"]["arguments"], dict):
                    tc["function"]["arguments"] = json.dumps(tc["function"]["arguments"])
        result.append(d)
    return result


def _parse_tool_calls(raw_tool_calls) -> list[ToolCall]:
    tcs = []
    for tc in (raw_tool_calls or []):
        try:
            args = json.loads(tc.function.arguments or "{}")
        except Exception:
            args = {}
        tcs.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))
    return tcs


class OpenAIClient(LLMClient):
    provider = "openai"

    def __init__(self, model_name: str | None = None, temperature: float = 0) -> None:
        model_name = model_name or os.getenv("OPENAI_MODEL_ID", "gpt-4o")
        super().__init__(model_name)
        self.temperature = temperature
        self.base_url = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        self.vision_model = os.getenv("OPENAI_VISION_MODEL_ID", model_name)
        self.client = OpenAI(
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=self.base_url,
        )

    def invoke(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> AIMessage:
        kwargs: dict = dict(
            model=self.model_name,
            messages=_messages_to_openai(messages),
            temperature=self.temperature,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**kwargs)
        choice = response.choices[0].message
        tool_calls = _parse_tool_calls(choice.tool_calls)
        return AIMessage(content=choice.content or "", tool_calls=tool_calls)

    def invoke_streaming(
        self,
        messages: list[AnyMessage],
        tools: list[dict] | None = None,
        chunk_queue: queue.Queue | None = None,
    ) -> AIMessage:
        """
        Stream response token-by-token. Text chunks are pushed to chunk_queue.
        Tool call arguments are accumulated from streaming deltas.
        Returns complete AIMessage when stream ends.
        """
        kwargs: dict = dict(
            model=self.model_name,
            messages=_messages_to_openai(messages),
            temperature=self.temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        # Accumulators
        accumulated_content: list[str] = []
        # Map index → {id, name, arguments_str}
        tc_accum: dict[int, dict] = {}

        try:
            for chunk in self.client.chat.completions.create(**kwargs):
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Text content — push each chunk to the queue immediately
                if delta.content:
                    accumulated_content.append(delta.content)
                    if chunk_queue is not None:
                        chunk_queue.put(delta.content)

                # Tool call deltas — accumulate across chunks
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in tc_accum:
                            tc_accum[idx] = {"id": "", "name": "", "arguments": ""}
                        if tc_delta.id:
                            tc_accum[idx]["id"] = tc_delta.id
                        if tc_delta.function:
                            if tc_delta.function.name:
                                tc_accum[idx]["name"] += tc_delta.function.name
                            if tc_delta.function.arguments:
                                tc_accum[idx]["arguments"] += tc_delta.function.arguments

        finally:
            if chunk_queue is not None:
                chunk_queue.put(None)  # sentinel — stream is done

        # Build final tool calls
        tool_calls: list[ToolCall] = []
        for idx in sorted(tc_accum.keys()):
            tc = tc_accum[idx]
            try:
                args = json.loads(tc["arguments"] or "{}")
            except Exception:
                args = {}
            tool_calls.append(ToolCall(id=tc["id"], name=tc["name"], arguments=args))

        return AIMessage(content="".join(accumulated_content), tool_calls=tool_calls)

    def stream(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> Iterator[str]:
        kwargs: dict = dict(
            model=self.model_name,
            messages=_messages_to_openai(messages),
            temperature=self.temperature,
            stream=True,
        )
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        for chunk in self.client.chat.completions.create(**kwargs):
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        response = self.client.chat.completions.create(
            model=self.vision_model,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ],
        )
        return response.choices[0].message.content or ""
