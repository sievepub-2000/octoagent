from __future__ import annotations

__all__ = [
    "make_lead_agent",
    "SandboxState",
    "ThreadState",
    "get_checkpointer",
    "reset_checkpointer",
    "make_checkpointer",
]


def __getattr__(name: str):
    if name == "make_lead_agent":
        from .lead_agent import make_lead_agent as _make_lead_agent
        return _make_lead_agent
    if name in {"get_checkpointer", "make_checkpointer", "reset_checkpointer"}:
        from .checkpointer import get_checkpointer, make_checkpointer, reset_checkpointer
        return {"get_checkpointer": get_checkpointer, "make_checkpointer": make_checkpointer, "reset_checkpointer": reset_checkpointer}[name]
    if name in {"SandboxState", "ThreadState"}:
        from .thread_state import SandboxState, ThreadState
        return {"SandboxState": SandboxState, "ThreadState": ThreadState}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
