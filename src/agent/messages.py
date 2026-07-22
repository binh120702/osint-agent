"""
Custom message types for the OSINT agent framework.
Replaces langchain.messages entirely.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SystemMessage:
    content: str
    role: str = "system"

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class HumanMessage:
    content: str
    role: str = "user"

    def to_dict(self) -> dict:
        return {"role": self.role, "content": self.content}


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict  # parsed JSON


@dataclass
class AIMessage:
    content: str
    role: str = "assistant"
    tool_calls: list[ToolCall] = field(default_factory=list)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {"role": self.role, "content": self.content}
        if self.tool_calls:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": tc.arguments,
                    },
                }
                for tc in self.tool_calls
            ]
        return d


@dataclass
class ToolMessage:
    content: str
    tool_call_id: str
    role: str = "tool"

    def to_dict(self) -> dict:
        return {
            "role": self.role,
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


# Union type alias used across the codebase
AnyMessage = SystemMessage | HumanMessage | AIMessage | ToolMessage


def to_dict(msg: AnyMessage) -> dict:
    """Serialize any message to an OpenAI-compatible dict."""
    return msg.to_dict()
