"""Streaming event helpers for the embedded OctoAgent client."""

from __future__ import annotations

import uuid
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage


class ClientStreamSerializer:
    """Serialize LangChain messages and state chunks into client events."""

    @staticmethod
    def serialize_message(msg) -> dict[str, Any]:
        if isinstance(msg, AIMessage):
            data: dict[str, Any] = {"type": "ai", "content": msg.content, "id": getattr(msg, "id", None)}
            if msg.tool_calls:
                data["tool_calls"] = [{"name": tc["name"], "args": tc["args"], "id": tc.get("id")} for tc in msg.tool_calls]
            return data
        if isinstance(msg, ToolMessage):
            return {
                "type": "tool",
                "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                "name": getattr(msg, "name", None),
                "tool_call_id": getattr(msg, "tool_call_id", None),
                "id": getattr(msg, "id", None),
            }
        if isinstance(msg, HumanMessage):
            return {"type": "human", "content": msg.content, "id": getattr(msg, "id", None)}
        if isinstance(msg, SystemMessage):
            return {"type": "system", "content": msg.content, "id": getattr(msg, "id", None)}
        return {"type": "unknown", "content": str(msg), "id": getattr(msg, "id", None)}

    @staticmethod
    def extract_text(content) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(block["text"])
            return "\n".join(parts) if parts else ""
        return str(content)

    @staticmethod
    def normalize_chunk_events(chunk, stream_event_cls):
        messages = chunk.get("messages", [])
        emitted_ai_text = chunk.get("_emitted_ai_text", {})
        emitted_ai_tool_calls = chunk.get("_emitted_ai_tool_calls", set())
        emitted_tool_messages = chunk.get("_emitted_tool_messages", set())
        events = []

        for index, msg in enumerate(messages):
            msg_id = getattr(msg, "id", None) or f"anonymous-{index}-{type(msg).__name__}"

            if isinstance(msg, AIMessage):
                if msg.tool_calls and msg_id not in emitted_ai_tool_calls:
                    emitted_ai_tool_calls.add(msg_id)
                    events.append(
                        stream_event_cls(
                            type="messages-tuple",
                            data={
                                "type": "ai",
                                "content": "",
                                "id": msg_id,
                                "tool_calls": [{"name": tc["name"], "args": tc["args"], "id": tc.get("id")} for tc in msg.tool_calls],
                            },
                        )
                    )
                text = ClientStreamSerializer.extract_text(msg.content)
                if text and emitted_ai_text.get(msg_id) != text:
                    emitted_ai_text[msg_id] = text
                    events.append(stream_event_cls(type="messages-tuple", data={"type": "ai", "content": text, "id": msg_id}))
            elif isinstance(msg, ToolMessage) and msg_id not in emitted_tool_messages:
                emitted_tool_messages.add(msg_id)
                events.append(
                    stream_event_cls(
                        type="messages-tuple",
                        data={
                            "type": "tool",
                            "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                            "name": getattr(msg, "name", None),
                            "tool_call_id": getattr(msg, "tool_call_id", None),
                            "id": msg_id,
                        },
                    )
                )

        events.append(
            stream_event_cls(
                type="values",
                data={
                    "title": chunk.get("title"),
                    "messages": [ClientStreamSerializer.serialize_message(m) for m in messages],
                    "artifacts": chunk.get("artifacts", []),
                },
            )
        )
        return events

    @staticmethod
    def fallback_events(*, message: str, reply, stream_event_cls):
        text = ClientStreamSerializer.extract_text(getattr(reply, "content", ""))
        if not text:
            raise ValueError("Direct model fallback produced empty content.")
        ai_id = getattr(reply, "id", None) or f"direct-ai-{uuid.uuid4()}"
        human = HumanMessage(content=message)
        return [
            stream_event_cls(type="messages-tuple", data={"type": "ai", "content": text, "id": ai_id}),
            stream_event_cls(
                type="values",
                data={
                    "title": None,
                    "messages": [
                        ClientStreamSerializer.serialize_message(human),
                        ClientStreamSerializer.serialize_message(AIMessage(content=text, id=ai_id)),
                    ],
                    "artifacts": [],
                },
            ),
            stream_event_cls(type="end", data={}),
        ]
