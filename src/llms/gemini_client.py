"""Gemini LLM client — direct google-genai SDK, no langchain."""
from __future__ import annotations

import json
import os
import uuid
from typing import Iterator

from dotenv import load_dotenv

from agent.messages import AnyMessage, AIMessage, ToolCall, SystemMessage
from llms.llm_client import LLMClient


load_dotenv()


class GeminiClient(LLMClient):
    def __init__(self, model_name: str | None = None, temperature: float = 0) -> None:
        model_name = model_name or os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash")
        super().__init__(model_name)
        self.temperature = temperature
        self.vision_model = os.getenv("GEMINI_VISION_MODEL_ID", model_name)

        try:
            import google.generativeai as genai
        except ImportError as e:
            raise RuntimeError(
                "Gemini provider selected but google-generativeai is not installed. "
                "Run: uv add google-generativeai"
            ) from e

        self._genai = genai
        genai.configure(api_key=os.getenv("GOOGLE_API_KEY", ""))

    def _build_model(self, model_name: str, tools_spec=None):
        kwargs = {"model_name": model_name}
        if self.temperature != 0:
            kwargs["generation_config"] = self._genai.types.GenerationConfig(temperature=self.temperature)
        if tools_spec:
            kwargs["tools"] = tools_spec
        return self._genai.GenerativeModel(**kwargs)

    def _messages_to_gemini(self, messages: list[AnyMessage]):
        """Convert our messages to Gemini SDK format."""
        system_parts = []
        history = []
        for m in messages:
            if isinstance(m, SystemMessage):
                system_parts.append(m.content)
            elif m.role == "user":
                history.append({"role": "user", "parts": [m.content]})
            elif m.role == "assistant":
                parts = []
                if m.content:
                    parts.append(m.content)
                # Gemini function calls would go here; simplified for now
                history.append({"role": "model", "parts": parts})
            elif m.role == "tool":
                # Gemini tool response
                history.append({
                    "role": "user",
                    "parts": [self._genai.types.FunctionResponse(
                        name=getattr(m, "_tool_name", "tool"),
                        response={"result": m.content}
                    )]
                })
        return system_parts, history

    def _openai_tools_to_gemini(self, tools: list[dict]):
        """Convert OpenAI tool schema format to Gemini FunctionDeclaration list."""
        declarations = []
        for t in tools:
            fn = t.get("function", {})
            declarations.append(self._genai.protos.FunctionDeclaration(
                name=fn["name"],
                description=fn.get("description", ""),
                parameters=self._genai.protos.Schema(
                    type=self._genai.protos.Type.OBJECT,
                    properties={
                        k: self._genai.protos.Schema(type=self._genai.protos.Type.STRING)
                        for k in fn.get("parameters", {}).get("properties", {})
                    },
                    required=fn.get("parameters", {}).get("required", []),
                ),
            ))
        return [self._genai.protos.Tool(function_declarations=declarations)]

    def invoke(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> AIMessage:
        system_parts, history = self._messages_to_gemini(messages)
        gemini_tools = self._openai_tools_to_gemini(tools) if tools else None
        model = self._build_model(self.model_name, tools_spec=gemini_tools)

        chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
        last = history[-1]["parts"][0] if history else ""
        response = chat.send_message(last)

        tool_calls: list[ToolCall] = []
        for part in response.parts:
            if hasattr(part, "function_call") and part.function_call:
                fc = part.function_call
                tool_calls.append(ToolCall(
                    id=str(uuid.uuid4()),
                    name=fc.name,
                    arguments=dict(fc.args),
                ))

        text = response.text if hasattr(response, "text") else ""
        return AIMessage(content=text or "", tool_calls=tool_calls)

    def invoke_streaming(
        self,
        messages: list[AnyMessage],
        tools: list[dict] | None = None,
        chunk_queue: queue.Queue | None = None,
    ) -> AIMessage:
        system_parts, history = self._messages_to_gemini(messages)
        gemini_tools = self._openai_tools_to_gemini(tools) if tools else None
        model = self._build_model(self.model_name, tools_spec=gemini_tools)

        chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
        last = history[-1]["parts"][0] if history else ""

        tool_calls: list[ToolCall] = []
        accumulated_text: list[str] = []

        try:
            response_stream = chat.send_message(last, stream=True)
            for chunk in response_stream:
                try:
                    text_chunk = chunk.text
                    if text_chunk:
                        accumulated_text.append(text_chunk)
                        if chunk_queue is not None:
                            chunk_queue.put(text_chunk)
                except Exception:
                    pass

                if hasattr(chunk, "parts") and chunk.parts:
                    for part in chunk.parts:
                        if hasattr(part, "function_call") and part.function_call:
                            fc = part.function_call
                            tool_calls.append(ToolCall(
                                id=str(uuid.uuid4()),
                                name=fc.name,
                                arguments=dict(fc.args),
                            ))
        finally:
            if chunk_queue is not None:
                chunk_queue.put(None)

        return AIMessage(content="".join(accumulated_text), tool_calls=tool_calls)

    def stream(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> Iterator[str]:
        system_parts, history = self._messages_to_gemini(messages)
        model = self._build_model(self.model_name)
        chat = model.start_chat(history=history[:-1] if len(history) > 1 else [])
        last = history[-1]["parts"][0] if history else ""
        for chunk in chat.send_message(last, stream=True):
            if chunk.text:
                yield chunk.text

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        import urllib.request
        # Gemini needs raw bytes for images
        model = self._build_model(self.vision_model)
        with urllib.request.urlopen(image_url) as r:
            image_bytes = r.read()
        response = model.generate_content([
            prompt,
            {"mime_type": "image/jpeg", "data": image_bytes},
        ])
        return response.text or ""
