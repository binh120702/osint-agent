
from dotenv import load_dotenv
import operator
from typing import Literal

from langchain.messages import AnyMessage, SystemMessage, ToolMessage
from typing_extensions import TypedDict, Annotated
from langgraph.graph import StateGraph, START, END

from tools.all_tools import get_all_tools
from llms.openai_client import OPENAI_CLIENT
from prompts import MAIN_PROMPT


load_dotenv()


class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]

def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """Decide if we should continue the loop or stop based on whether the LLM made a tool call."""
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "tool_node"

    return END

def tool_node(state: dict):
    """Performs the tool call"""

    result = []
    for tool_call in state["messages"][-1].tool_calls:
        tool = TOOLS_BY_NAME[tool_call["name"]]
        observation = tool.invoke(tool_call["args"])
        result.append(ToolMessage(content=observation, tool_call_id=tool_call["id"]))
    return {"messages": result}

def llm_call(state: dict):
    """Single LLM step that may decide to call tools."""
    return {
        "messages": [
            CLIENT_WITH_TOOLS.invoke(
                [
                    SystemMessage(
                        content=MAIN_PROMPT
                    )
                ]
                + state["messages"]
            )
        ]
    }


def _init_tools():
    tools = get_all_tools()
    tools_by_name = {tool.name: tool for tool in tools}
    client_with_tools = OPENAI_CLIENT.client.bind_tools(tools, tool_choice="auto")
    return tools, tools_by_name, client_with_tools


TOOLS, TOOLS_BY_NAME, CLIENT_WITH_TOOLS = _init_tools()


def build_graph() -> StateGraph:
    graph = StateGraph(MessagesState)
    graph.add_node("llm_call", llm_call)
    graph.add_node("tool_node", tool_node)
    graph.add_edge(START, "llm_call")
    graph.add_conditional_edges("llm_call", should_continue, ["tool_node", END])
    graph.add_edge("tool_node", "llm_call")
    return graph.compile()


graph = build_graph()