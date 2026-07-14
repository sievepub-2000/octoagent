"""Native desktop driver tools backed by pyautogui or xdotool."""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langchain.tools import tool

from src.gateway.observability import record_exception_trace, record_tool_trace
from src.tools.builtins.system_ops_tools import _artifact_dir
from src.utils.serialization import fmt_json as _json


def _pyautogui_importable() -> bool:
    return importlib.util.find_spec("pyautogui") is not None


def _driver() -> str | None:
    if _pyautogui_importable():
        return "pyautogui"
    if shutil.which("xdotool"):
        return "xdotool"
    return None


def _configured_display() -> str | None:
    return os.environ.get("OCTOAGENT_DESKTOP_DISPLAY") or os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or None


def _configured_xauthority() -> str | None:
    value = os.environ.get("OCTOAGENT_DESKTOP_XAUTHORITY") or os.environ.get("XAUTHORITY")
    if not value:
        return None
    path = Path(value).expanduser()
    return str(path) if path.exists() else None


def _x11_socket_count() -> int:
    root = Path("/tmp/.X11-unix")
    if not root.exists():
        return 0
    return sum(1 for item in root.iterdir() if item.is_socket())


def _desktop_env() -> dict[str, str]:
    env = os.environ.copy()
    display = _configured_display()
    if display:
        env["DISPLAY"] = display
        os.environ.setdefault("DISPLAY", display)
    xauthority = _configured_xauthority()
    if xauthority:
        env["XAUTHORITY"] = xauthority
        os.environ.setdefault("XAUTHORITY", xauthority)
    return env


def _display_available() -> bool:
    return bool(_configured_display())


def _run(args: list[str], *, timeout: int = 10) -> dict[str, Any]:
    env = _desktop_env()
    record_tool_trace(
        "subprocess_start",
        tool="desktop_driver",
        args=args,
        timeout=timeout,
        display=env.get("DISPLAY"),
    )
    try:
        result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", timeout=timeout, check=False, env=env)
    except Exception as exc:
        record_exception_trace("desktop_driver._run", exc, args=args)
        return {"success": False, "status": "transport_error", "detail": str(exc)}
    return {
        "success": result.returncode == 0,
        "exit_code": result.returncode,
        "stdout": (result.stdout or "").strip()[:1200],
        "stderr": (result.stderr or "").strip()[:1200],
    }


def desktop_driver_status() -> dict[str, Any]:
    driver = _driver()
    display = _configured_display()
    return {
        "available": driver is not None and bool(display),
        "driver": driver,
        "display": display,
        "display_available": bool(display),
        "xauthority_configured": _configured_xauthority() is not None,
        "x11_socket_count": _x11_socket_count(),
        "pyautogui_importable": _pyautogui_importable(),
        "xdotool_path": shutil.which("xdotool"),
        "note": "Desktop actions require system permission mode plus OCTOAGENT_DESKTOP_DISPLAY/DISPLAY access to a graphical session.",
    }


@tool("desktop_driver_status", parse_docstring=True)
def desktop_driver_status_tool() -> str:
    """Return native desktop driver availability for pyautogui/xdotool."""

    return _json(desktop_driver_status())


@tool("desktop_screenshot", parse_docstring=True)
def desktop_screenshot_tool(output_name: str | None = None) -> str:
    """Capture a native desktop screenshot to a runtime artifact.

    Args:
        output_name: Optional artifact directory name.
    """

    status = desktop_driver_status()
    if not status["display_available"]:
        return _json({"success": False, "status": "display_unavailable", **status})
    artifact_dir = _artifact_dir("desktop_screenshot", output_name)
    path = artifact_dir / f"screenshot-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}.png"
    driver = status["driver"]
    if driver == "pyautogui":
        try:
            _desktop_env()
            import pyautogui  # type: ignore

            pyautogui.FAILSAFE = True
            image = pyautogui.screenshot()
            image.save(path)
            return _json({"success": True, "driver": "pyautogui", "path": str(path)})
        except Exception as exc:
            record_exception_trace("desktop_screenshot.pyautogui", exc)
            return _json({"success": False, "driver": "pyautogui", "status": "capture_failed", "detail": str(exc)})
    for cmd in (["gnome-screenshot", "-f", str(path)], ["import", "-window", "root", str(path)], ["scrot", str(path)]):
        if shutil.which(cmd[0]):
            result = _run(cmd, timeout=15)
            result.update({"driver": cmd[0], "path": str(path)})
            return _json(result)
    return _json({"success": False, "status": "driver_unavailable", **status})


@tool("desktop_click", parse_docstring=True)
def desktop_click_tool(x: int, y: int, button: str = "left") -> str:
    """Click an absolute desktop coordinate.

    Args:
        x: Screen x coordinate.
        y: Screen y coordinate.
        button: Mouse button: left, middle, or right.
    """

    status = desktop_driver_status()
    if not status["available"]:
        return _json({"success": False, "status": "driver_unavailable", **status})
    button_map = {"left": 1, "middle": 2, "right": 3}
    normalized_button = button.lower().strip()
    if normalized_button not in button_map:
        return _json({"success": False, "status": "invalid_button", "allowed": sorted(button_map)})
    if status["driver"] == "pyautogui":
        try:
            _desktop_env()
            import pyautogui  # type: ignore

            pyautogui.FAILSAFE = True
            pyautogui.click(int(x), int(y), button=normalized_button)
            return _json({"success": True, "driver": "pyautogui", "x": int(x), "y": int(y), "button": normalized_button})
        except Exception as exc:
            record_exception_trace("desktop_click.pyautogui", exc, x=x, y=y, button=button)
            return _json({"success": False, "driver": "pyautogui", "status": "click_failed", "detail": str(exc)})
    return _json(_run(["xdotool", "mousemove", str(int(x)), str(int(y)), "click", str(button_map[normalized_button])]))


@tool("desktop_type_text", parse_docstring=True)
def desktop_type_text_tool(text: str, interval_ms: int = 0) -> str:
    """Type text into the currently focused native desktop control.

    Args:
        text: Text to type.
        interval_ms: Delay between characters in milliseconds, capped at 500.
    """

    status = desktop_driver_status()
    if not status["available"]:
        return _json({"success": False, "status": "driver_unavailable", **status, "text_length": len(text)})
    delay = max(0, min(int(interval_ms), 500)) / 1000
    if status["driver"] == "pyautogui":
        try:
            _desktop_env()
            import pyautogui  # type: ignore

            pyautogui.FAILSAFE = True
            pyautogui.write(text, interval=delay)
            return _json({"success": True, "driver": "pyautogui", "text_length": len(text)})
        except Exception as exc:
            record_exception_trace("desktop_type_text.pyautogui", exc, text_length=len(text))
            return _json({"success": False, "driver": "pyautogui", "status": "type_failed", "detail": str(exc)})
    return _json(_run(["xdotool", "type", "--delay", str(int(delay * 1000)), text], timeout=max(10, min(60, len(text) // 20 + 10))))


@tool("desktop_hotkey", parse_docstring=True)
def desktop_hotkey_tool(keys: str) -> str:
    """Press a desktop keyboard shortcut.

    Args:
        keys: Shortcut like ctrl+c, ctrl+shift+t, or alt+tab.
    """

    status = desktop_driver_status()
    if not status["available"]:
        return _json({"success": False, "status": "driver_unavailable", **status, "keys": keys})
    normalized = keys.strip().lower().replace(" ", "")
    parts = [part for part in re_split_hotkey(normalized) if part]
    if not parts:
        return _json({"success": False, "status": "invalid_hotkey"})
    if status["driver"] == "pyautogui":
        try:
            _desktop_env()
            import pyautogui  # type: ignore

            pyautogui.FAILSAFE = True
            pyautogui.hotkey(*parts)
            return _json({"success": True, "driver": "pyautogui", "keys": parts})
        except Exception as exc:
            record_exception_trace("desktop_hotkey.pyautogui", exc, keys=keys)
            return _json({"success": False, "driver": "pyautogui", "status": "hotkey_failed", "detail": str(exc)})
    return _json(_run(["xdotool", "key", "+".join(parts)]))


def re_split_hotkey(value: str) -> list[str]:
    return value.replace(",", "+").split("+")


@tool("desktop_scroll", parse_docstring=True)
def desktop_scroll_tool(clicks: int) -> str:
    """Scroll the native desktop at the current cursor location.

    Args:
        clicks: Positive scrolls up, negative scrolls down. Absolute value is capped at 20.
    """

    status = desktop_driver_status()
    if not status["available"]:
        return _json({"success": False, "status": "driver_unavailable", **status})
    count = max(-20, min(20, int(clicks)))
    if count == 0:
        return _json({"success": True, "status": "noop", "clicks": 0})
    if status["driver"] == "pyautogui":
        try:
            _desktop_env()
            import pyautogui  # type: ignore

            pyautogui.FAILSAFE = True
            pyautogui.scroll(count)
            return _json({"success": True, "driver": "pyautogui", "clicks": count})
        except Exception as exc:
            record_exception_trace("desktop_scroll.pyautogui", exc, clicks=count)
            return _json({"success": False, "driver": "pyautogui", "status": "scroll_failed", "detail": str(exc)})
    button = "4" if count > 0 else "5"
    results = [_run(["xdotool", "click", button]) for _ in range(abs(count))]
    return _json({"success": all(result.get("success") for result in results), "driver": "xdotool", "clicks": count, "results": results[-3:]})


DESKTOP_DRIVER_TOOLS = [
    desktop_driver_status_tool,
    desktop_screenshot_tool,
    desktop_click_tool,
    desktop_type_text_tool,
    desktop_hotkey_tool,
    desktop_scroll_tool,
]

__all__ = ["DESKTOP_DRIVER_TOOLS", "desktop_driver_status"]
