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


def from_dict(d: dict) -> AnyMessage:
    """Reconstruct a Message object from a dictionary representation."""
    role = d.get("role")
    content = d.get("content", "")
    if role == "system":
        return SystemMessage(content=content)
    elif role == "user":
        return HumanMessage(content=content)
    elif role == "assistant":
        tool_calls = []
        if "tool_calls" in d:
            for tc in d["tool_calls"]:
                func = tc.get("function", {})
                args = func.get("arguments", {})
                if isinstance(args, str):
                    import json
                    try:
                        args = json.loads(args)
                    except Exception:
                        pass
                tool_calls.append(ToolCall(
                    id=tc.get("id", ""),
                    name=func.get("name", ""),
                    arguments=args
                ))
        return AIMessage(content=content, tool_calls=tool_calls)
    elif role == "tool":
        return ToolMessage(content=content, tool_call_id=d.get("tool_call_id", ""))
    raise ValueError(f"Unknown message role: {role}")
