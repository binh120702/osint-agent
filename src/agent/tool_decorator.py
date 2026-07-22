"""
Lightweight @tool decorator — replaces langchain.tools.tool.

Usage is identical to the langchain version:

    @tool
    def my_tool(query: str) -> str:
        '''Short description shown to LLM.'''
        return do_work(query)

The decorator adds:
    my_tool.name          — function name
    my_tool.description   — docstring (first paragraph)
    my_tool.schema        — OpenAI-compatible JSON schema for the function
    my_tool.invoke(args)  — call with a dict or kwargs (mirrors LangChain interface)
"""
from __future__ import annotations

import inspect
import json
import textwrap
from functools import wraps
from typing import Any, Callable, get_type_hints


# ── Python type → JSON Schema type ──────────────────────────────────────────

_PY_TO_JSON: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _py_type_to_json(annotation: Any) -> str:
    """Convert a basic Python annotation to a JSON Schema type string."""
    if annotation in _PY_TO_JSON:
        return _PY_TO_JSON[annotation]
    # Handle Optional[X], Union[X, None], etc.
    origin = getattr(annotation, "__origin__", None)
    if origin is not None:
        args = getattr(annotation, "__args__", ())
        # Flatten away NoneType for Optional
        non_none = [a for a in args if a is not type(None)]
        if non_none:
            return _py_type_to_json(non_none[0])
    return "string"  # safe fallback


def _build_schema(fn: Callable) -> dict:
    """Build an OpenAI function-calling compatible JSON schema from a function."""
    sig = inspect.signature(fn)

    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    # Extract parameter descriptions from the docstring (Google style / plain)
    doc = inspect.getdoc(fn) or ""
    param_docs: dict[str, str] = {}
    in_args = False
    for line in doc.splitlines():
        stripped = line.strip()
        if stripped.lower() in ("args:", "arguments:", "parameters:", "params:"):
            in_args = True
            continue
        if in_args:
            if stripped and not stripped.startswith(" ") and stripped.endswith(":") and " " not in stripped[:-1]:
                # New section header — stop
                in_args = False
                continue
            if ":" in stripped:
                parts = stripped.split(":", 1)
                param_name = parts[0].strip()
                param_desc = parts[1].strip()
                if param_name in sig.parameters:
                    param_docs[param_name] = param_desc

    properties: dict[str, dict] = {}
    required: list[str] = []

    for name, param in sig.parameters.items():
        if name == "self":
            continue
        ann = hints.get(name, str)
        json_type = _py_type_to_json(ann)
        prop: dict[str, Any] = {"type": json_type}
        if name in param_docs:
            prop["description"] = param_docs[name]
        properties[name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(name)

    return {
        "type": "function",
        "function": {
            "name": fn.__name__,
            "description": textwrap.dedent(doc).strip().split("\n\n")[0].replace("\n", " "),
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


# ── Decorator ────────────────────────────────────────────────────────────────

def tool(fn: Callable) -> Callable:
    """Decorate a function as an agent tool."""

    @wraps(fn)
    def wrapper(*args, **kwargs):
        return fn(*args, **kwargs)

    # Attach metadata
    wrapper.name = fn.__name__  # type: ignore[attr-defined]
    wrapper.description = (inspect.getdoc(fn) or "").split("\n\n")[0].strip()  # type: ignore[attr-defined]
    wrapper.schema = _build_schema(fn)  # type: ignore[attr-defined]

    def invoke(args_or_dict: dict | None = None, **kw) -> Any:
        """Call the tool. Accepts a dict of args or keyword arguments."""
        if args_or_dict is None:
            args_or_dict = {}
        if isinstance(args_or_dict, str):
            # Some callers pass raw JSON string
            try:
                args_or_dict = json.loads(args_or_dict)
            except Exception:
                args_or_dict = {}
        merged = {**args_or_dict, **kw}
        return fn(**merged)

    wrapper.invoke = invoke  # type: ignore[attr-defined]

    return wrapper
