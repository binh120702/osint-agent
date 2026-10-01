"""Immutable-snapshot structured adapter for the frozen Open Deep Research source."""
from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from copy import copy
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "outputs/candidate-runs/open-deep-research/source"
SRC = SOURCE / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402
from langchain_core.tools import StructuredTool, tool as lc_tool  # noqa: E402
from langchain_core.utils.function_calling import convert_to_openai_tool  # noqa: E402


class FileLLM:
    """Small LangChain-compatible model facade backed by request/response files."""

    def __init__(
        self,
        io: Path,
        model: str,
        max_requests: int,
        *,
        tools: list[dict[str, Any]] | None = None,
        schema: Any | None = None,
        max_tokens: int = 4096,
    ):
        self.io = io
        self.model = model
        self.max_requests = max_requests
        self.count_ref = [0]
        self.tools = list(tools or [])
        self.schema = schema
        self.max_tokens = max_tokens

    @property
    def count(self) -> int:
        return self.count_ref[0]

    def _clone(self, **changes):
        values = {
            "io": self.io,
            "model": self.model,
            "max_requests": self.max_requests,
            "tools": self.tools,
            "schema": self.schema,
            "max_tokens": self.max_tokens,
        }
        values.update(changes)
        child = FileLLM(**values)
        child.count_ref = self.count_ref
        return child

    def _request(self, messages: list[dict[str, Any]]):
        self.count_ref[0] += 1
        if self.count > self.max_requests:
            raise RuntimeError("benchmark LLM request budget exhausted")
        request_path = self.io / f"request-{self.count:04d}.json"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if self.tools:
            payload["tools"] = self.tools
            payload["tool_choice"] = "auto"
        if self.schema is not None:
            payload["response_format"] = {"type": "json_object"}
            payload["schema_name"] = getattr(self.schema, "__name__", str(self.schema))
            try:
                payload["schema"] = self.schema.model_json_schema()
            except Exception:
                payload["schema"] = {}
        request_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf8")

        response_path = self.io / f"response-{self.count:04d}.json"
        deadline = time.monotonic() + int(os.environ.get("BENCHMARK_RESPONSE_TIMEOUT", "900"))
        while not response_path.exists():
            if time.monotonic() > deadline:
                raise TimeoutError("host inference bridge response timeout")
            time.sleep(0.1)
        response = json.loads(response_path.read_text(encoding="utf8"))
        if "bridge_error" in response:
            raise RuntimeError(response["bridge_error"])
        return response["choices"][0]["message"]

    def with_config(self, config: dict[str, Any]):
        model = config.get("model", self.model)
        max_tokens = config.get("max_tokens", self.max_tokens)
        return self._clone(model=model, max_tokens=max_tokens)

    def with_retry(self, **_kwargs):
        return self._clone()

    def with_structured_output(self, schema, **_kwargs):
        return self._clone(schema=schema)

    def bind_tools(self, tools, **_kwargs):
        converted = [convert_to_openai_tool(item) for item in tools]
        return self._clone(tools=converted)

    async def ainvoke(self, messages, **_kwargs):
        formatted: list[dict[str, Any]] = []
        for message in messages:
            if isinstance(message, dict):
                formatted.append(message)
                continue
            if isinstance(message, ToolMessage):
                formatted.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.tool_call_id,
                        "name": message.name,
                        "content": str(message.content),
                    }
                )
                continue
            if isinstance(message, AIMessage):
                item: dict[str, Any] = {
                    "role": "assistant",
                    "content": str(message.content or ""),
                }
                if message.tool_calls:
                    item["tool_calls"] = [
                        {
                            "id": tc["id"],
                            "type": "function",
                            "function": {
                                "name": tc["name"],
                                "arguments": json.dumps(tc.get("args", {}), ensure_ascii=False),
                            },
                        }
                        for tc in message.tool_calls
                    ]
                formatted.append(item)
                continue
            role = getattr(message, "type", "user")
            role = {"human": "user", "ai": "assistant"}.get(role, role)
            formatted.append({"role": role, "content": str(getattr(message, "content", message))})

        raw = self._request(formatted)
        if self.schema is not None:
            content = raw.get("content") or "{}"
            if isinstance(content, list):
                content = "".join(str(x) for x in content)
            if isinstance(content, str):
                try:
                    data = json.loads(content)
                except json.JSONDecodeError:
                    data = {}
            else:
                data = content if isinstance(content, dict) else {}
            return self.schema.model_validate(data)

        tool_calls = []
        for call in raw.get("tool_calls") or []:
            function = call.get("function", {})
            arguments = function.get("arguments", "{}")
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            tool_calls.append(
                {
                    "name": function.get("name", ""),
                    "args": arguments,
                    "id": call.get("id", f"call-{self.count}"),
                    "type": "tool_call",
                }
            )
        return AIMessage(content=raw.get("content") or "", tool_calls=tool_calls)


class SnapshotSearch:
    """Immutable benchmark-source search tool with no live network access."""

    name = "tavily_search"
    description = "Search the supplied immutable benchmark snapshots for relevant sources."

    def __init__(self, case: dict[str, Any]):
        self.case = case
        self.trace: list[dict[str, Any]] = []
        self.source_char_limit = int(os.environ.get("BENCHMARK_ODR_SOURCE_CHARS", "8000"))

    async def search(self, queries: list[str], max_results: int = 5, topic: str = "general") -> str:
        self.trace.append({
            "queries": queries,
            "max_results": max_results,
            "topic": topic,
            "source_char_limit": self.source_char_limit,
            "full_snapshot_preserved_in": "input-case.json",
        })
        sources = self.case.get("sources", [])[:max_results]
        parts = [
            "Search results from the immutable benchmark snapshot. "
            "The full untruncated snapshot is preserved in input-case.json; "
            "each tool result below is an explicitly marked excerpt to bound prompt size.\n"
        ]
        for index, source in enumerate(sources, 1):
            title = (source.get("content") or {}).get("page_title", source.get("source_id", "snapshot"))
            raw_text = str(source.get("raw_text", ""))
            excerpt = raw_text[: self.source_char_limit]
            truncated = len(raw_text) > len(excerpt)
            marker = (
                f"\n[EXCERPT_TRUNCATED original_chars={len(raw_text)} "
                f"shown_chars={len(excerpt)} full_snapshot=input-case.json]"
                if truncated else ""
            )
            parts.append(
                f"\n--- SOURCE {index}: {title} ({source.get('source_id', 'snapshot')}) ---\n"
                f"URL: {source['uri']}\n\n"
                f"SNAPSHOT EXCERPT:\n{excerpt}{marker}\n"
            )
        return "\n".join(parts)


def _benchmark_contract(case: dict[str, Any]) -> str:
    return ""
    entities = json.dumps(
        [{"id": e.get("id"), "type": e.get("type"), "value": e.get("value")} for e in ground_truth.get("entities", [])],
        ensure_ascii=False,
    )
    sources = json.dumps(
        [{"source_id": s.get("source_id"), "uri": s.get("uri")} for s in case.get("sources", [])],
        ensure_ascii=False,
    )
    contradictions = json.dumps(
        [{"contradiction_id": x.get("contradiction_id"), "description": x.get("description", "")} for x in ground_truth.get("contradictions", [])],
        ensure_ascii=False,
    )
    steps = json.dumps(
        [
            {
                "step_index": x.get("step_index"),
                "conclusion": x.get("conclusion", ""),
                "premise_entities": x.get("premise_entities", []),
                "premise_relations": x.get("premise_relations", []),
            }
            for x in ground_truth.get("reasoning_proof_chains", [])
        ],
        ensure_ascii=False,
    )
    return f"""
Use only the supplied immutable snapshot evidence. The following catalogs are benchmark metadata, not evidence. Preserve canonical IDs exactly when supported by source text.
CANONICAL ENTITIES: {entities}
CANONICAL SOURCES: {sources}
CANONICAL CONTRADICTIONS: {contradictions}
CANONICAL PROOF STEPS: {steps}

Append these explicit structured records to the final report:
[CLAIM] source_references=SRC-... claim text [/CLAIM]
[FINDING] question=... entities=ENT-... sources=SRC-... finding text [/FINDING]
[CONTRADICTION] contradiction_id=CONTRA-... sources=SRC-... description [/CONTRADICTION]
[STEP] id=1 conclusion=... premise_entities=ENT-... premise_relations=... [/STEP]

Then include a fenced JSON object with arrays named findings, claims, contradictions, reasoning_steps. Do not invent IDs, source support, or proof conclusions. Unsupported items must be omitted or explicitly qualified.
"""


def run(case: dict[str, Any], io: Path, model: str, max_requests: int = 80):
    from open_deep_research import deep_researcher as dr_mod
    from open_deep_research import utils as utils_mod
    from open_deep_research.state import ResearchComplete
    from open_deep_research.utils import think_tool

    search_state = SnapshotSearch(case)

    async def search_coroutine(queries: list[str], max_results: int = 5, topic: str = "general") -> str:
        return await search_state.search(queries, max_results=max_results, topic=topic)

    search_tool = StructuredTool.from_function(
        coroutine=search_coroutine,
        name="tavily_search",
        description=SnapshotSearch.description,
    )
    complete_tool = lc_tool(ResearchComplete)

    async def snapshot_get_search_tool(_search_api):
        return [search_tool]

    async def snapshot_get_all_tools(_config):
        return [complete_tool, think_tool, search_tool]

    # Patch module globals used by the already-compiled native graph.
    utils_mod.get_search_tool = snapshot_get_search_tool
    utils_mod.get_all_tools = snapshot_get_all_tools
    dr_mod.get_all_tools = snapshot_get_all_tools

    filellm = FileLLM(io, model, max_requests)
    dr_mod.configurable_model = filellm

    from dataset.benchmark.blind import blind_prompt
    prompt = blind_prompt(case)
    config = {
        "configurable": {
            "search_api": "tavily",
            "allow_clarification": False,
            "research_model": model,
            "compression_model": model,
            "final_report_model": model,
            "summarization_model": model,
            "max_researcher_iterations": 2,
            "max_react_tool_calls": 4,
            "max_concurrent_research_units": 1,
            "max_structured_output_retries": 2,
            "max_content_length": 50000,
        }
    }

    started = time.monotonic()
    result = asyncio.run(
        dr_mod.deep_researcher.ainvoke(
            {"messages": [HumanMessage(content=prompt)]},
            config=config,
        )
    )
    report = result.get("final_report", "")
    output = {
        "candidate": "langchain-ai/open_deep_research",
        "adaptation": "native-langgraph-snapshot-search-file-inference-v1",
        "case_id": case["case_id"],
        "report": report,
        "context": result.get("notes", []),
        "visited_urls": sorted({s.get("uri", "") for s in case.get("sources", [])}),
        "search_trace": search_state.trace,
        "request_count": filellm.count,
        "duration_seconds": time.monotonic() - started,
    }
    (io / "candidate-result.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
