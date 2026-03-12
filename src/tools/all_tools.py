import json
from pathlib import Path
from typing import Dict

from tools.deep_search import deep_search
from tools.engine_search import engine_search_tool
from tools.final_report import final_report
from tools.github_tools import github_repo_summary, github_search_repos
from tools.image_descriptor import describe_image
from tools.knowledge_base import kb_extract_entities, kb_get
from tools.pinterest import pinterest_scrape_by_username
from tools.web_content_tools import get_url_content
from tools.wiki_tools import wiki_fetch_page, wiki_search_pages


TOOLS: Dict[str, object] = {
    "pinterest_scrape_by_username": pinterest_scrape_by_username,
    "deep_search": deep_search,
    "engine_search_tool": engine_search_tool,
    "get_url_content": get_url_content,
    "wiki_fetch_page": wiki_fetch_page,
    "wiki_search_pages": wiki_search_pages,
    "github_repo_summary": github_repo_summary,
    "github_search_repos": github_search_repos,
    "describe_image": describe_image,
    "final_report": final_report,
    "kb_extract_entities": kb_extract_entities,
    "kb_get": kb_get,
}


def _load_tool_config() -> Dict[str, bool]:
    """
    Load tool enable/disable flags from tool_config.json (next to this file).

    The config is a JSON object mapping tool names to booleans.
    Missing keys default to True. Unknown keys are ignored.
    """
    default_config: Dict[str, bool] = {name: True for name in TOOLS.keys()}
    config_path = Path(__file__).with_name("tool_config.json")

    if not config_path.exists():
        return default_config

    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        # If the file is invalid, fall back to all tools enabled
        return default_config

    merged = default_config.copy()
    for name, value in raw.items():
        if name in merged and isinstance(value, bool):
            merged[name] = value
    return merged


def get_all_tools():
    """
    Return the list of tools that should be exposed to the agent.

    This is controlled by src/tools/tool_config.json so users can
    toggle individual tools on or off without changing code.
    """
    config = _load_tool_config()
    return [tool for name, tool in TOOLS.items() if config.get(name, True)]