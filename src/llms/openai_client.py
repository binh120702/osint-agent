from dotenv import load_dotenv

from langchain.messages import AnyMessage
from langchain_openai import ChatOpenAI
from openai import OpenAI

from llms.llm_client import LLMClient
import os


# Ensure environment variables from .env are loaded
load_dotenv()


class OpenAIClient(LLMClient):
    def __init__(self, model_name: str | None = None, temperature: float = 0) -> None:
        if model_name is None:
            model_name = os.getenv("OPENAI_MODEL_ID", "gpt-5.4")
        self.model_name = model_name
        self.base_url = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        self.client = ChatOpenAI(model=model_name, temperature=temperature, base_url=self.base_url)
        self.vision_model = os.getenv("OPENAI_VISION_MODEL_ID", "gpt-4.1-nano-2025-04-14")
        self.raw_client = OpenAI(
            base_url=self.base_url,
            api_key=os.getenv("OPENAI_API_KEY"),
        )

    def invoke(self, messages: list[AnyMessage]) -> AnyMessage:
        return self.client.invoke(messages)

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        response = self.raw_client.responses.create(
            model=self.vision_model,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": prompt},
                        {"type": "input_image", "image_url": image_url},
                    ],
                }
            ],
        )
        return getattr(response, "output_text", "") or ""