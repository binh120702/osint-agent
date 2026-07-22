"""Factory that builds and caches the active LLM client based on env vars."""
from __future__ import annotations

import os
from dotenv import load_dotenv

from llms.llm_client import LLMClient


load_dotenv()


def build_llm_client() -> LLMClient:
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()

    if provider == "openai":
        from llms.openai_client import OpenAIClient
        return OpenAIClient(model_name=os.getenv("OPENAI_MODEL_ID", "gpt-4o"))

    if provider == "gemini":
        from llms.gemini_client import GeminiClient
        return GeminiClient(model_name=os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash"))

    if provider in {"claude", "anthropic"}:
        from llms.claude_client import ClaudeClient
        return ClaudeClient(model_name=os.getenv("CLAUDE_MODEL_ID", "claude-sonnet-4-5"))

    raise ValueError(
        f"Unsupported LLM_PROVIDER '{provider}'. Use one of: openai, gemini, claude."
    )


ACTIVE_LLM_CLIENT: LLMClient = build_llm_client()
