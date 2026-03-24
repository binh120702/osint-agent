import os

from llms.llm_client import LLMClient
from llms.openai_client import OpenAIClient


def build_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if provider == "openai":
        return OpenAIClient(model_name=os.getenv("OPENAI_MODEL_ID", "gpt-5.4"))

    if provider == "gemini":
        from llms.gemini_client import GeminiClient

        return GeminiClient(model_name=os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash"))

    if provider in {"claude", "anthropic"}:
        from llms.claude_client import ClaudeClient

        return ClaudeClient(
            model_name=os.getenv("CLAUDE_MODEL_ID", "claude-3-5-sonnet-latest")
        )

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. Use one of: openai, gemini, claude."
    )


ACTIVE_LLM_CLIENT = build_llm_client()

