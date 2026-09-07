"""Offline source replay and temporary production-tool overrides."""

from __future__ import annotations

import json
import re
import unicodedata
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
        self.query_trace: list[dict[str, Any]] = []
        self._stopwords = {"the", "and", "for", "with", "from", "that", "this", "what", "who", "how", "are"}

    def _evidence_content(self, source: dict[str, Any]) -> dict[str, Any]:
        excluded = {"evidence_summary", "supports_findings", "confidence", "source_quality",
                    "verification_status", "retrieved_sha256", "snapshot_status", "publisher",
                    "publication_date", "fetch_date", "fetch_status", "fetch_content_type",
                    "date_accessed", "verification_notes", "evidence_summary_is_source_text"}
        return {key: value for key, value in (source.get("content") or {}).items() if key not in excluded}

    def _tokens(self, value: Any) -> list[str]:
        text = unicodedata.normalize("NFKC", str(value or "")).casefold()
        return [x for x in re.findall(r"[\w.-]+", text) if len(x) > 2 and x not in self._stopwords]

    def search(self, query: str, page: int = 1, page_size: int = 10) -> str:
        page = max(1, int(page or 1)); page_size = max(1, min(100, int(page_size or 10)))
        query_tokens = self._tokens(query)
        phrase = " ".join(query_tokens)
        ranked = []
        for source in self.sources:
            content = self._evidence_content(source)
            title = str(content.get("page_title", ""))
            raw = str(source.get("raw_text", ""))
            uri = str(source.get("uri", ""))
            title_tokens, raw_tokens, uri_tokens = set(self._tokens(title)), set(self._tokens(raw)), set(self._tokens(uri))
            score = sum(10 for _ in [1] if phrase and phrase in title.casefold())
            score += sum(6 for _ in [1] if phrase and phrase in raw.casefold())
            score += sum(4 for token in query_tokens if token in uri_tokens)
            score += sum(1 for token in query_tokens if token in raw_tokens)
            if score: ranked.append((score, source))
        ranked.sort(key=lambda item: (-item[0], item[1]["source_id"]))
        total = len(ranked); begin = (page - 1) * page_size
        selected = ranked[begin:begin + page_size]
        results = [{"title": self._evidence_content(source).get("page_title", source["source_id"]), "url": source["uri"],
                    "snippet": source.get("raw_text", "")[:1000], "source": "benchmark", "source_id": source["source_id"]}
                   for _, source in selected]
        record = {"query": str(query), "page": page, "page_size": page_size,
                  "returned_source_ids": [x["source_id"] for _, x in selected], "total": total}
        self.query_trace.append(record)
        return json.dumps({"query": query, "page": page, "page_size": page_size, "total": total,
                           "sources": {"benchmark": results}, "merged_results": results, "errors": {}}, ensure_ascii=False, indent=2)

    def fetch(self, url: str) -> str:
        source = self.by_uri.get(_uri_key(url))
        if not source:
            return json.dumps({"success": False, "error": "Source is not present in the offline case snapshot", "url": url})
        # Content summaries, confidence labels, and supports_findings are
        # curator annotations, not source evidence. Keep them out of replay.
        evidence_content = self._evidence_content(source)
        return json.dumps({
            "success": True,
            "url": source["uri"],
            "source_id": source["source_id"],
            "title": evidence_content.get("page_title", source["source_id"]),
            "content": evidence_content,
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
            "engine_search_tool": lambda query, page=1, page_size=10: self.replay.search(query, page, page_size),
            "get_url_content": lambda url: self.replay.fetch(url),
            "deep_search": lambda pages=None, *args, **kwargs: json.dumps({
                "success": bool(pages),
                "pages": [json.loads(self.replay.fetch(page)) for page in (pages or [])],
                "query_trace": self.replay.query_trace,
                "error": "No pages supplied" if not pages else None,
            }, ensure_ascii=False, indent=2),
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
