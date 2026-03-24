import os

from dotenv import load_dotenv
from langchain.messages import AnyMessage

from llms.llm_client import LLMClient


load_dotenv()


class ClaudeClient(LLMClient):
    def __init__(self, model_name: str | None = None, temperature: float = 0) -> None:
        if model_name is None:
            model_name = os.getenv("CLAUDE_MODEL_ID", "claude-3-5-sonnet-latest")
        self.model_name = model_name
        self.vision_model = os.getenv("CLAUDE_VISION_MODEL_ID", model_name)

        try:
            from langchain_anthropic import ChatAnthropic
        except Exception as e:
            raise RuntimeError(
                "Claude provider selected but langchain-anthropic is not installed."
            ) from e

        self.client = ChatAnthropic(
            model=model_name,
            temperature=temperature,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        )
        self.vision_client = ChatAnthropic(
            model=self.vision_model,
            temperature=0,
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
        )

    def invoke(self, messages: list[AnyMessage]) -> AnyMessage:
        return self.client.invoke(messages)

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        response = self.vision_client.invoke(
            [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                }
            ]
        )
        return getattr(response, "content", str(response))

