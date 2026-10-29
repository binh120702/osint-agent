import importlib
import json
from pathlib import Path
from typing import Dict

from agent.tool_decorator import get_registered_tools


# Only import purpose-built tool modules. Other files in this package include
# legacy utilities with optional dependencies and are not agent tools.
TOOL_MODULES = (
    "tools.pinterest",
    "tools.deep_search",
    "tools.engine_search",
    "tools.web_content_tools",
    "tools.wiki_tools",
    "tools.github_tools",
    "tools.image_descriptor",
    "tools.final_report",
    "tools.knowledge_base",
)


def discover_tools() -> Dict[str, object]:
    """Import declared modules and return their decorated tools by name."""
    for module_name in TOOL_MODULES:
        importlib.import_module(module_name)

    registered_tools = get_registered_tools()
    allowed_modules = set(TOOL_MODULES)
    tools = {
        name: registered
        for name, registered in registered_tools.items()
        if getattr(registered, "tool_module", "") in allowed_modules
    }
    for name, registered in tools.items():
        schema = getattr(registered, "schema", None)
        if not name or not isinstance(schema, dict) or schema.get("function", {}).get("name") != name:
            raise ValueError(f"Tool {name!r} has an invalid function schema")
        if not callable(getattr(registered, "invoke", None)):
            raise ValueError(f"Tool {name!r} does not implement invoke(args)")
    return tools


TOOLS: Dict[str, object] = discover_tools()


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
    if not isinstance(raw, dict):
        return default_config

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
