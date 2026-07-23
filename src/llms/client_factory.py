"""Factory that builds and caches the active LLM client based on env vars."""
from __future__ import annotations

import os
from dotenv import load_dotenv

from llms.llm_client import LLMClient


load_dotenv()


def get_llm_client_for(provider: str | None = None, model_name: str | None = None) -> LLMClient:
    """Build a specific LLM Client dynamically, falling back to env configurations."""
    prov = (provider or os.getenv("LLM_PROVIDER", "openai")).strip().lower()

    if prov == "openai":
        from llms.openai_client import OpenAIClient
        model = model_name or os.getenv("OPENAI_MODEL_ID", "gpt-4o")
        return OpenAIClient(model_name=model)

    if prov == "gemini":
        from llms.gemini_client import GeminiClient
        model = model_name or os.getenv("GEMINI_MODEL_ID", "gemini-2.5-flash")
        return GeminiClient(model_name=model)

    if prov in {"claude", "anthropic"}:
        from llms.claude_client import ClaudeClient
        model = model_name or os.getenv("CLAUDE_MODEL_ID", "claude-sonnet-4-5")
        return ClaudeClient(model_name=model)

    raise ValueError(
        f"Unsupported LLM provider '{prov}'. Use one of: openai, gemini, claude."
    )


def build_llm_client() -> LLMClient:
    return get_llm_client_for()


ACTIVE_LLM_CLIENT: LLMClient = build_llm_client()
