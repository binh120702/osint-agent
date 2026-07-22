"""Abstract LLM client interface — no langchain dependency."""
from __future__ import annotations

import queue
from abc import ABC, abstractmethod
from typing import Iterator

from agent.messages import AnyMessage, AIMessage


class LLMClient(ABC):
    """Abstract interface for all LLM clients."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @abstractmethod
    def invoke(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> AIMessage:
        """Send messages to the model and return a single AIMessage response (blocking)."""
        raise NotImplementedError

    @abstractmethod
    def invoke_streaming(
        self,
        messages: list[AnyMessage],
        tools: list[dict] | None = None,
        chunk_queue: queue.Queue | None = None,
    ) -> AIMessage:
        """
        Send messages and stream the text response token-by-token.

        Text chunks are pushed into ``chunk_queue`` as ``str`` items as they
        arrive.  A ``None`` sentinel is put into the queue when the stream is
        complete.  The method returns the complete ``AIMessage`` (including any
        tool_calls) when done.

        If ``chunk_queue`` is None, behaves like ``invoke()``.
        """
        raise NotImplementedError

    @abstractmethod
    def stream(self, messages: list[AnyMessage], tools: list[dict] | None = None) -> Iterator[str]:
        """Stream text chunks from the model. Yields str deltas."""
        raise NotImplementedError

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the identifier for the underlying model."""
        raise NotImplementedError

    @abstractmethod
    def describe_image(self, image_url: str, prompt: str) -> str:
        """Describe an image URL using the underlying provider."""
        raise NotImplementedError
