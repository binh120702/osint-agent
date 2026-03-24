import os

from dotenv import load_dotenv
from langchain.messages import AnyMessage

from llms.llm_client import LLMClient


load_dotenv()


class GeminiClient(LLMClient):
    def __init__(self, model_name: str | None = None, temperature: float = 0) -> None:
        if model_name is None:
            model_name = os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash")
        self.model_name = model_name
        self.vision_model = os.getenv("GEMINI_VISION_MODEL_ID", model_name)

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except Exception as e:
            raise RuntimeError(
                "Gemini provider selected but langchain-google-genai is not installed."
            ) from e

        self.client = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=temperature,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )
        self.vision_client = ChatGoogleGenerativeAI(
            model=self.vision_model,
            temperature=0,
            google_api_key=os.getenv("GOOGLE_API_KEY"),
        )

    def invoke(self, messages: list[AnyMessage]) -> AnyMessage:
        return self.client.invoke(messages)

    def get_model_name(self) -> str:
        return self.model_name

    def describe_image(self, image_url: str, prompt: str) -> str:
        # Gemini's LC wrapper supports multimodal content via dict blocks.
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

