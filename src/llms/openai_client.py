from dotenv import load_dotenv

from langchain.messages import AnyMessage
from langchain_openai import ChatOpenAI

from llms.llm_client import LLMClient
import os


# Ensure environment variables from .env are loaded
load_dotenv()


class OpenAIClient(LLMClient):
    def __init__(self, model_name: str = "gpt-5.4", temperature: float = 0) -> None:
        self.model_name = model_name
        self.base_url = os.getenv("OPENAI_API_BASE_URL", "https://api.openai.com/v1")
        self.client = ChatOpenAI(model=model_name, temperature=temperature, base_url=self.base_url)

    def invoke(self, messages: list[AnyMessage]) -> AnyMessage:
        return self.client.invoke(messages)

    def get_model_name(self) -> str:
        return self.model_name


OPENAI_CLIENT = OpenAIClient()