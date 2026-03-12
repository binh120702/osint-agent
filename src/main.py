
from dotenv import load_dotenv
import operator
import os
from typing import Literal, Any

from langchain.messages import AnyMessage, SystemMessage, ToolMessage
from typing_extensions import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END

from tools.all_tools import get_all_tools
from llms.openai_client import OPENAI_CLIENT
from prompts import MAIN_PROMPT


load_dotenv()


class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]


TOOLS_BY_NAME = {}
CLIENT_WITH_TOOLS = None
_LAST_TOOL_NAMES: list[str] = []

_MAX_TOOL_CHARS = int(os.getenv("OSINT_MAX_TOOL_CHARS", "8000"))


def _truncate_observation(observation: Any) -> Any:
    """
    Restrict tool results so they don't overflow the LLM context.

    - For strings: truncate to _MAX_TOOL_CHARS characters and append a notice.
    - For non-strings: leave as-is (LangChain will handle serialization).
    """
    if not isinstance(observation, str):
        return observation

    if len(observation) <= _MAX_TOOL_CHARS:
        return observation

    suffix = "\n\n[tool output truncated to avoid context overflow]"
    keep = _MAX_TOOL_CHARS - len(suffix)
    if keep <= 0:
        return suffix
    return observation[:keep] + suffix


def _refresh_tools_if_needed() -> None:
    """
    Refresh the bound tools if the enabled tool set has changed.

    This lets UI-driven changes to src/tools/tool_config.json take effect
    without restarting the LangGraph server.
    """
    global TOOLS_BY_NAME, CLIENT_WITH_TOOLS, _LAST_TOOL_NAMES

    tools = get_all_tools()
    current_names = sorted(tool.name for tool in tools)

    if current_names == _LAST_TOOL_NAMES and CLIENT_WITH_TOOLS is not None:
        return

    TOOLS_BY_NAME = {tool.name: tool for tool in tools}
    CLIENT_WITH_TOOLS = OPENAI_CLIENT.client.bind_tools(tools, tool_choice="auto")
    _LAST_TOOL_NAMES = current_names


def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based on whether the LLM made a tool call."""
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "tool_node"

    return END


def tool_node(state: dict):
    """Performs the tool call."""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = TOOLS_BY_NAME[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        observation = _truncate_observation(observation)
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}


def llm_call(state: dict):
    """Single LLM step that may decide to call tools."""
    _refresh_tools_if_needed()
    return {
        "messages": [
            CLIENT_WITH_TOOLS.invoke(
                [SystemMessage(content=MAIN_PROMPT)] + state["messages"]
            )
        ]
    }


def build_graph() -> StateGraph:
    graph = StateGraph(MessagesState)
    graph.add_node("llm_call", llm_call)
    graph.add_node("tool_node", tool_node)
    graph.add_edge(START, "llm_call")
    graph.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    graph.add_edge("tool_node", "llm_call")
    return graph.compile()


graph = build_graph()