from dotenv import load_dotenv

from langchain.messages import AnyMessage
from langchain_openai import ChatOpenAI

from llms.llm_client import LLMClient


# Ensure environment variables from .env are loaded
load_dotenv()


class OpenAIClient(LLMClient):
    def __init__(self, model_name: str = "gpt-4.1-mini", temperature: float = 0) -> None:
        self.model_name = model_name
        self.client = ChatOpenAI(model=model_name, temperature=temperature)

    def invoke(self, messages: list[AnyMessage]) -> AnyMessage:
        return self.client.invoke(messages)

    def get_model_name(self) -> str:
        return self.model_name


OPENAI_CLIENT = OpenAIClient()