from abc import ABC, abstractmethod

from langchain.messages import AnyMessage


class LLMClient(ABC):
    """Abstract interface for all LLM clients."""

    def __init__(self, model_name: str) -> None:
        self.model_name = model_name

    @abstractmethod
    def invoke(self, messages: list[AnyMessage]) -> AnyMessage:
        """Send a list of messages to the underlying model and return its response."""
        raise NotImplementedError

    @abstractmethod
    def get_model_name(self) -> str:
        """Return the identifier for the underlying model."""
        raise NotImplementedError

    @abstractmethod
    def describe_image(self, image_url: str, prompt: str) -> str:
        """Describe an image URL using the underlying provider."""
        raise NotImplementedError
