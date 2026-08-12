"""Claude (Anthropic) LLM client — direct anthropic SDK, no langchain."""
from __future__ import annotations

import json
import os
import queue
from typing import Iterator

from dotenv import load_dotenv

from agent.messages import AnyMessage, AIMessage, ToolCall, SystemMessage
from llms.llm_client import LLMClient


load_dotenv()


def _messages_to_anthropic(messages: list[AnyMessage]) -> tuple[str, list[dict]]:
    """Split system message out and convert remaining to Anthropic format."""
    system_content = ""
    chat_messages: list[dict] = []

    for m in messages:
        if isinstance(m, SystemMessage):
            system_content += m.content + "\n"
            continue

        if m.role == "user":
            chat_messages.append({"role": "user", "content": m.content})

        elif m.role == "assistant":
            content: list[dict] = []
            if m.content:
                content.append({"type": "text", "text": m.content})
            for tc in (m.tool_calls or []):
                args = tc.arguments if isinstance(tc.arguments, dict) else json.loads(tc.arguments or "{}")
                content.append({
                    "type": "tool_use",
                    "id": tc.id,
                    "name": tc.name,
                    "input": args,
                })
            chat_messages.append({"role": "assistant", "content": content})

        elif m.role == "tool":
            chat_messages.append({
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": m.tool_call_id,
                        "content": m.content,
                    }
                ],
            })

    return system_content.strip(), chat_messages


def _openai_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """Convert OpenAI tool schema to Anthropic format."""
    result = []
    for t in tools:
        fn = t.get("function", {})
        result.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


class ClaudeClient(LLMClient):
    provider = "claude"

    def __init__(self, model_name: str | None = None, temperature: float = 0) -> None:
        model_name = model_name or os.getenv("CLAUDE_MODEL_ID", "claude-sonnet-4-5")
        super().__init__(model_name)
        self.temperature = temperature
        self.vision_model = os.getenv("CLAUDE_VISION_MODEL_ID", model_name)

        try:
            import anthropic
            self._anthropic = anthropic
            self.client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        except ImportError as e:
            raise RuntimeError(
                "Claude provider selected but anthropic SDK is not installed. "
                "Run: uv add anthropic"
            ) from e

    def invoke(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> AIMessage:
        system_text, chat_msgs = _messages_to_anthropic(messages)
        kwargs: dict = dict(
            model=self.model_name,
            max_tokens=8192,
            messages=chat_msgs,
            temperature=self.temperature,
        )
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = _openai_tools_to_anthropic(tools)

        response = self.client.messages.create(**kwargs)

        text_parts = []
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input if isinstance(block.input, dict) else {},
                ))

        return AIMessage(content="\n".join(text_parts), tool_calls=tool_calls)

    def invoke_streaming(
        self,
        messages: list[AnyMessage],
        tools: list[dict] | None = None,
        chunk_queue: queue.Queue | None = None,
    ) -> AIMessage:
        """
        Stream response via Claude's streaming API.
        Text deltas are pushed to chunk_queue immediately.
        Tool use blocks (which only arrive at end) are collected from the
        final message. Returns complete AIMessage when stream ends.
        """
        system_text, chat_msgs = _messages_to_anthropic(messages)
        kwargs: dict = dict(
            model=self.model_name,
            max_tokens=8192,
            messages=chat_msgs,
            temperature=self.temperature,
        )
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = _openai_tools_to_anthropic(tools)

        accumulated_text: list[str] = []
        tool_calls: list[ToolCall] = []

        try:
            with self.client.messages.stream(**kwargs) as stream:
                # text_stream yields only text deltas — push each token immediately
                for text_chunk in stream.text_stream:
                    accumulated_text.append(text_chunk)
                    if chunk_queue is not None:
                        chunk_queue.put(text_chunk)

                # After the stream closes, grab the final message for tool_use blocks
                final_msg = stream.get_final_message()
                for block in final_msg.content:
                    if block.type == "tool_use":
                        tool_calls.append(ToolCall(
                            id=block.id,
                            name=block.name,
                            arguments=block.input if isinstance(block.input, dict) else {},
                        ))
        finally:
            if chunk_queue is not None:
                chunk_queue.put(None)  # sentinel

        return AIMessage(content="".join(accumulated_text), tool_calls=tool_calls)

    def stream(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> Iterator[str]:
        system_text, chat_msgs = _messages_to_anthropic(messages)
        kwargs: dict = dict(
            model=self.model_name,
            max_tokens=8192,
            messages=chat_msgs,
            temperature=self.temperature,
        )
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = _openai_tools_to_anthropic(tools)

        with self.client.messages.stream(**kwargs) as stream:
            for text in stream.text_stream:
                yield text

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        import urllib.request
        import base64
        with urllib.request.urlopen(image_url) as r:
            image_data = r.read()
        b64 = base64.standard_b64encode(image_data).decode("utf-8")
        response = self.client.messages.create(
            model=self.vision_model,
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/jpeg", "data": b64},
                    },
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        return response.content[0].text if response.content else ""
