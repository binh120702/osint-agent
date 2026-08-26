"""Offline source replay and temporary production-tool overrides."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from typing import Any
from urllib.parse import urlsplit, urlunsplit


def _uri_key(value: Any) -> str:
    parsed = urlsplit(str(value or "").strip())
    if not parsed.scheme or not parsed.netloc:
        return str(value or "").strip().casefold().rstrip("/")
    return urlunsplit((parsed.scheme.casefold(), parsed.netloc.casefold(), parsed.path.rstrip("/"), parsed.query, ""))


class SourceReplay:
    def __init__(self, case: dict[str, Any]):
        self.case = case
        self.sources = list(case.get("sources", []))
        self.by_uri = {_uri_key(item["uri"]): item for item in self.sources}

    def search(self, query: str) -> str:
        words = {word.casefold() for word in str(query).split() if len(word) > 2}
        ranked = []
        for source in self.sources:
            haystack = " ".join([
                str(source.get("uri", "")),
                str(source.get("raw_text", "")),
                json.dumps(source.get("content", {}), ensure_ascii=False),
            ]).casefold()
            score = sum(word in haystack for word in words)
            if score:
                ranked.append((score, source))
        ranked.sort(key=lambda item: (-item[0], item[1]["source_id"]))
        results = [
            {
                "title": source.get("content", {}).get("page_title", source["source_id"]),
                "url": source["uri"],
                "snippet": source.get("content", {}).get("evidence_summary", source.get("raw_text", ""))[:1000],
                "source": "benchmark",
                "source_id": source["source_id"],
            }
            for _, source in ranked
        ]
        return json.dumps({"query": query, "sources": {"benchmark": results}, "merged_results": results, "errors": {}}, ensure_ascii=False, indent=2)

    def fetch(self, url: str) -> str:
        source = self.by_uri.get(_uri_key(url))
        if not source:
            return json.dumps({"success": False, "error": "Source is not present in the offline case snapshot", "url": url})
        return json.dumps({
            "success": True,
            "url": source["uri"],
            "source_id": source["source_id"],
            "title": source.get("content", {}).get("page_title", source["source_id"]),
            "content": source.get("content", {}),
            "raw_text": source.get("raw_text", ""),
        }, ensure_ascii=False, indent=2)


class _ToolOverride:
    def __init__(self, original: Any, handler):
        self.name = original.name
        self.description = original.description
        self.schema = original.schema
        self._handler = handler

    def invoke(self, args: dict[str, Any]) -> str:
        return self._handler(**args)


class OfflineToolOverrides(AbstractContextManager):
    """Replace network-facing tools only for the duration of one benchmark run."""

    def __init__(self, replay: SourceReplay):
        self.replay = replay
        self._originals: dict[str, Any] = {}

    def __enter__(self):
        from tools import all_tools

        handlers = {
            "engine_search_tool": lambda query: self.replay.search(query),
            "get_url_content": lambda url: self.replay.fetch(url),
            "deep_search": lambda pages=None, *args, **kwargs: self.replay.fetch(pages[0] if pages else "")
            if pages else json.dumps({"success": False, "error": "No pages supplied", "pages": []}),
        }
        for name, handler in handlers.items():
            original = all_tools.TOOLS.get(name)
            if original is not None:
                self._originals[name] = original
                all_tools.TOOLS[name] = _ToolOverride(original, handler)
        return self

    def __exit__(self, exc_type, exc, traceback):
        from tools import all_tools
        all_tools.TOOLS.update(self._originals)
        return False
