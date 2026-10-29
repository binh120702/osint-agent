# OSINT Agent

## Adding an agent tool

Tools are Python functions decorated with `@tool`. The decorator registers the function and provides the JSON schema and `.invoke(args)` interface used by the agent.

```python
from agent.tool_decorator import tool


@tool
def lookup_public_profile(username: str, limit: int = 10) -> str:
    """Look up public information for a username.

    Args:
        username: Account name to investigate.
        limit: Maximum number of results.
    """
    ...
```

Contributor checklist:

1. Put the function in a focused module under `src/tools/`; use an existing module where it fits, or create a new one.
2. Import `tool` from `agent.tool_decorator` and decorate each function intended for the agent. Every tool needs a docstring; its first paragraph is shown to the model. Document parameters in an `Args:` section.
3. If you created a module, add its fully-qualified name to `TOOL_MODULES` in `src/tools/all_tools.py`. This explicit allowlist prevents legacy helpers and modules with optional dependencies from being imported as agent tools.
4. Add the tool name to `src/tools/tool_config.json` with `true` to enable it by default. Existing configuration keys can disable tools without code changes.
5. From the repository root, run `python -m unittest discover -s tests -p 'test_*.py'` and `python -m unittest discover -s src/tests -p 'test_*.py'`, then smoke-test the tool through the app.

Tool functions should validate inputs, handle expected network/service failures, return a useful string (JSON is suitable for structured results), and avoid printing results. Keep credentials in environment/configuration, never in source. The agent expects each tool to expose a unique function name, an OpenAI-compatible `.schema`, and `.invoke(args)`; registration/schema errors fail during startup rather than silently creating an unusable tool.
