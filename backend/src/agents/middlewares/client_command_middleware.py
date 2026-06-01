"""Middleware that injects a server-approved client execution contract."""

from __future__ import annotations

import json
import re
from collections.abc import Awaitable, Callable
from typing import Any, override
from urllib.parse import quote

from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelCallResult, ModelRequest, ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from src.agents.dialogue_routing import classify_dialogue_route


class ClientCommandMiddleware(AgentMiddleware[AgentState]):
    """Expose normalized client intent as hidden context before the agent runs."""

    @override
    def before_agent(self, state: AgentState, runtime: Runtime) -> dict[str, Any] | None:
        runtime_context = runtime.context or {}
        client_command = runtime_context.get("client_command")
        governance = runtime_context.get("session_governance")
        messages = list(state.get("messages", []))
        if not messages:
            return None
        last_message = messages[-1]
        if not isinstance(last_message, HumanMessage):
            return None

        # The conversation middleware never pre-computes or injects a
        # user-facing answer (e.g. weather/tool "snapshots"), and never tells
        # the model to skip tools for fresh-information requests. Pre-baked
        # answers caused parroting, stale-city leaks, and "answer without
        # reading the question" failures that generalize far beyond weather.
        # The model owns the answer; tools own the facts; this middleware only
        # supplies neutral context (route guards + governance metadata).
        if not isinstance(client_command, dict):
            return None
        route_kind = _route_kind(runtime_context) or classify_dialogue_route(str(last_message.content)).kind
        if route_kind in {"control_command", "plan_only"}:
            messages[-1:-1] = [_build_control_route_guard(route_kind)]
            return {"messages": messages}

        contract_lines = ["<client_execution_contract>"]
        contract_lines.append("Client translated the latest user turn into a normalized operation contract. Server remains authoritative for approval, sandboxing, execution, and final output.")
        contract_lines.append(f"Operation ID: {client_command.get('operation_id', 'unknown')}")
        contract_lines.append(f"Intent: {client_command.get('intent', 'conversation')}")
        contract_lines.append(f"Execution target: {client_command.get('execution_target', 'repo_read')}")
        if client_command.get("cli_scope"):
            contract_lines.append(f"CLI scope: {client_command['cli_scope']}")
        if client_command.get("command_text"):
            contract_lines.append(f"Requested command: {client_command['command_text']}")
        if client_command.get("requested_url"):
            contract_lines.append(f"Requested URL: {client_command['requested_url']}")
        if client_command.get("requested_path"):
            contract_lines.append(f"Requested path: {client_command['requested_path']}")
        if client_command.get("requested_app"):
            contract_lines.append(f"Requested app: {client_command['requested_app']}")
        notes = client_command.get("notes") or []
        if isinstance(notes, list) and notes:
            contract_lines.append("Client notes:")
            contract_lines.extend(f"- {note}" for note in notes)

        if isinstance(governance, dict):
            goal_drift = governance.get("goal_drift") or {}
            contract_lines.append(f"Continuation mode: {governance.get('continuation_mode', 'fresh')}")
            contract_lines.append(f"Context pressure: {governance.get('context_pressure', 'low')}")
            contract_lines.append(f"Recommended memory action: {governance.get('recommended_memory_action', 'continue')}")
            contract_lines.append(f"Goal drift status: {goal_drift.get('status', 'aligned')}")
            if goal_drift.get("reason"):
                contract_lines.append(f"Goal drift reason: {goal_drift['reason']}")
            if governance.get("continuity_summary"):
                contract_lines.append(f"Continuation summary: {governance['continuity_summary']}")
        contract_lines.append("</client_execution_contract>")

        # Insert contract as a SystemMessage before the last HumanMessage
        # instead of mutating the HumanMessage content (which would leak
        # the raw XML into the chat stream visible to the user).
        contract_msg = SystemMessage(content="\n".join(contract_lines))
        messages[-1:-1] = [contract_msg]
        return {"messages": messages}

    @override
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelCallResult:
        instant = _build_instant_client_answer(request.messages, request.runtime.context or {})
        if instant is not None:
            return ModelResponse(result=[AIMessage(content=instant)])
        return handler(request)

    @override
    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelCallResult:
        instant = _build_instant_client_answer(request.messages, request.runtime.context or {})
        if instant is not None:
            return ModelResponse(result=[AIMessage(content=instant)])
        return await handler(request)


def _route_kind(runtime_context: dict[str, Any]) -> str | None:
    route = runtime_context.get("dialogue_route")
    if isinstance(route, dict):
        return route.get("kind")
    return route if isinstance(route, str) else None


def _last_human_text(messages: list[Any]) -> str:
    for message in reversed(messages):
        if isinstance(message, HumanMessage) or getattr(message, "type", None) == "human":
            content = getattr(message, "content", "")
            if isinstance(content, list):
                return " ".join(str(part.get("text", "")) for part in content if isinstance(part, dict))
            return str(content)
    return ""


def _extract_tagged_json(messages: list[Any], tag: str) -> dict[str, Any] | None:
    pattern = re.compile(rf"<{tag}>\s*(.*?)\s*</{tag}>", re.DOTALL)
    for message in reversed(messages):
        content = getattr(message, "content", "")
        if not isinstance(content, str) or f"<{tag}>" not in content:
            continue
        match = pattern.search(content)
        if not match:
            continue
        body = match.group(1)
        json_match = re.search(r"(\{[\s\S]*\})", body)
        if not json_match:
            continue
        try:
            payload = json.loads(json_match.group(1))
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _build_instant_client_answer(messages: list[Any], runtime_context: dict[str, Any]) -> str | None:
    user_text = _last_human_text(messages)
    route = _route_kind(runtime_context) or classify_dialogue_route(user_text).kind
    if route == "control_command":
        return _format_control_command_answer(user_text)
    # "current_snapshot" intentionally no longer short-circuits the model.
    # Real-time/factual answers must flow through the model + tool loop so the
    # response is grounded in THIS turn's request and freshly fetched data.
    if route == "direct_answer":
        return _try_direct_arithmetic_answer(user_text)
    return None


def _build_control_route_guard(route_kind: str) -> SystemMessage:
    if route_kind == "control_command":
        guidance = (
            "The latest user turn is a conversation control command. "
            "Acknowledge the control intent briefly. Do not run tools or claim external actions unless an explicit runtime control API is invoked outside the model."
        )
    else:
        guidance = (
            "The latest user turn is planning-only or confirmation-gated. "
            "Provide analysis, options, and a proposed plan only. Do not execute tools, modify files, run commands, commit, push, or start background work until the user confirms."
        )
    return SystemMessage(content=f"<dialogue_control_guard>\n{guidance}\n</dialogue_control_guard>")


def _format_control_command_answer(user_text: str) -> str | None:
    text = user_text.strip().lower()
    if not text:
        return None
    if "/new" in text or "新对话" in user_text or "新会话" in user_text or "新聊天" in user_text or text == "new":
        return "已识别为新对话控制命令。请使用 WebUI 的新对话入口；当前回合不会启动工具执行。"
    if "/status" in text or text == "status" or "状态" in user_text or "进度" in user_text:
        return "已识别为状态查询控制命令。当前回合不会启动新的工具执行。"
    if "/stop" in text or "/pause" in text or text in {"stop", "pause"} or any(word in user_text for word in ("暂停", "停止", "停下", "中止", "取消")):
        return "已识别为停止/暂停控制命令。当前回合不会启动新的工具执行。"
    if "/resume" in text or "/continue" in text or text in {"resume", "continue"} or any(word in user_text for word in ("继续", "接着", "恢复")):
        return "已识别为继续/恢复控制命令。需要恢复具体任务时，请明确要继续的任务或确认继续上一项待执行工作。"
    return "已识别为对话控制命令。当前回合不会启动工具执行。"


def _try_direct_arithmetic_answer(user_text: str) -> str | None:
    text = user_text.strip()
    match = re.fullmatch(
        r"(?:请直接回答[:：]?\s*)?(-?\d+(?:\.\d+)?)\s*([+\-*/×÷])\s*(-?\d+(?:\.\d+)?)\s*(?:等于|=)?\s*(?:是多少|是几|多少|几)?\s*[?？]?",
        text,
    )
    if not match:
        return None
    left = float(match.group(1))
    op = match.group(2)
    right = float(match.group(3))
    if op in {"/", "÷"} and right == 0:
        return "除数不能为 0。"
    if op == "+":
        value = left + right
    elif op == "-":
        value = left - right
    elif op in {"*", "×"}:
        value = left * right
    else:
        value = left / right
    if value.is_integer():
        value_text = str(int(value))
    else:
        value_text = f"{value:.8g}"
    return f"{match.group(1)}{op}{match.group(3)}等于{value_text}。"


_WEATHER_CONDITION_ZH = {
    "clear": "晴",
    "partly cloudy": "多云",
    "fog": "有雾",
    "drizzle": "毛毛雨",
    "rain": "有雨",
    "snow": "有雪",
    "thunderstorm": "雷雨",
    "unknown": "未知",
}


def _format_weather_answer(payload: dict[str, Any]) -> str:
    forecasts = payload.get("forecasts")
    if not isinstance(forecasts, list) or not forecasts:
        error = payload.get("error") or "没有可用的天气快照。"
        return f"当前无法获取天气数据：{error}"

    lines: list[str] = []
    source = payload.get("source") or "weather snapshot"
    for forecast in forecasts:
        if not isinstance(forecast, dict):
            continue
        city = forecast.get("requested_name") or forecast.get("city") or "未知城市"
        days = forecast.get("days")
        if not isinstance(days, list) or not days:
            error = forecast.get("error") or forecast.get("fallback_error") or "没有返回预报数据"
            lines.append(f"{city}: 暂无可用预报（{error}）。")
            continue
        lines.append(f"{city}:")
        for day in days:
            if not isinstance(day, dict):
                continue
            condition = str(day.get("condition") or "unknown")
            condition_zh = _WEATHER_CONDITION_ZH.get(condition.lower(), condition)
            max_temp = day.get("temperature_max_c")
            min_temp = day.get("temperature_min_c")
            rain = day.get("precipitation_probability_max_percent")
            lines.append(f"- {day.get('date')}: {condition_zh}, 最高 {max_temp}°C, 最低 {min_temp}°C, 降水概率 {rain}%")
    if not lines:
        return "当前天气快照为空，无法给出可靠预报。"
    return "\n".join(lines) + f"\n来源：{source}。"


def _maybe_build_system_tools_snapshot(user_text: str) -> SystemMessage | None:
    if not _is_system_tools_inventory_request(user_text):
        return None

    payload: dict[str, Any]
    try:
        from src.tools.registry.service import ToolRegistryService

        registry = ToolRegistryService().build_registry()
        items = []
        seen: set[str] = set()
        for tool in registry.builtin_tools:
            name = str(tool.name)
            if not name or name in seen:
                continue
            seen.add(name)
            description = str(tool.description or "").strip().split("\n", 1)[0]
            items.append(
                {
                    "name": name,
                    "description": description[:180],
                    "category": _categorize_tool_name(name),
                    "surface": "builtin",
                }
            )
        for server in registry.mcp:
            name = f"mcp:{server.name}"
            if name in seen:
                continue
            seen.add(name)
            items.append(
                {
                    "name": name,
                    "description": (server.description or "")[:180],
                    "category": "mcp",
                    "surface": "mcp",
                    "enabled": server.enabled,
                    "transport": server.transport,
                }
            )
        payload = {
            "source": "OctoAgent runtime tool registry",
            "summary": registry.summary.model_dump(),
            "total": len(items),
            "tools": items,
        }
    except Exception as exc:
        payload = {
            "source": "OctoAgent runtime tool registry",
            "error": str(exc),
            "total": 0,
            "tools": [],
        }

    return SystemMessage(
        content=(
            "<system_tools_snapshot>\n"
            "The latest user request asks for this OctoAgent server's internal tool inventory. "
            "Use this server-fetched runtime snapshot directly. Do not use web search for this question.\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
            "</system_tools_snapshot>"
        )
    )


def _is_system_tools_inventory_request(user_text: str) -> bool:
    lower = user_text.lower()
    has_inventory_trigger = bool(
        re.search(r"\b(available tools?|tool inventory|tool status|system tools?)\b", lower)
        or any(token in user_text for token in ("系统工具", "工具情况", "可用工具", "工具列表", "工具清单", "工具状态"))
    )
    if not has_inventory_trigger:
        return False

    execution_markers = (
        "call ",
        "execute",
        "run ",
        "use ",
        "invoke",
        "test",
        "verify",
        "smoke",
        "执行",
        "运行",
        "调用",
        "使用",
        "测试",
        "验证",
        "试用",
        "是否正常使用",
        "能否正常",
    )
    return not any(marker in lower or marker in user_text for marker in execution_markers)


def _categorize_tool_name(name: str) -> str:
    lower = name.lower()
    if "web" in lower or "search" in lower or "fetch" in lower or "reader" in lower:
        return "web"
    if "file" in lower or lower in {"ls", "read_file", "write_file", "str_replace"}:
        return "file"
    if "image" in lower or "vision" in lower:
        return "image"
    if "task" in lower or "subagent" in lower:
        return "agent"
    if "document" in lower or "convert" in lower:
        return "document"
    if "shell" in lower or "bash" in lower or "codex" in lower:
        return "execution"
    if lower.startswith("mcp:"):
        return "mcp"
    return "other"


def _format_system_tools_answer(payload: dict[str, Any]) -> str:
    if payload.get("error"):
        return f"当前无法读取系统工具注册表：{payload['error']}"
    tools = payload.get("tools")
    if not isinstance(tools, list) or not tools:
        return "当前系统工具注册表为空，或运行时未加载任何工具。"

    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in tools:
        if isinstance(item, dict):
            grouped.setdefault(str(item.get("category") or "other"), []).append(item)

    category_labels = {
        "web": "网页/搜索",
        "file": "文件",
        "image": "图像",
        "agent": "Agent/任务",
        "document": "文档",
        "execution": "执行",
        "mcp": "MCP 服务",
        "other": "其他",
    }
    lines = [f"当前系统已加载 {payload.get('total', len(tools))} 个工具："]
    summary = payload.get("summary")
    if isinstance(summary, dict):
        lines.append(
            "- 汇总："
            f"内置工具 {summary.get('builtin_tools_total', 0)}，"
            f"MCP {summary.get('mcp_enabled', 0)}/{summary.get('mcp_total', 0)} 启用，"
            f"技能 {summary.get('skills_enabled', 0)}/{summary.get('skills_total', 0)} 启用，"
            f"插件 {summary.get('plugins_enabled', 0)}/{summary.get('plugins_total', 0)} 启用。"
        )
    for category in ("web", "file", "execution", "document", "image", "agent", "mcp", "other"):
        entries = grouped.get(category) or []
        if not entries:
            continue
        names = ", ".join(f"`{entry.get('name')}`" for entry in entries[:16])
        more = f" 等 {len(entries)} 个" if len(entries) > 16 else ""
        lines.append(f"- {category_labels.get(category, category)}：{names}{more}")
    lines.append("来源：OctoAgent 当前运行时工具注册表。")
    return "\n".join(lines)


_KNOWN_WEATHER_CITIES: dict[str, dict[str, object]] = {
    "tokyo": {
        "name": "Tokyo",
        "aliases": ("tokyo", "東京", "东京"),
        "lat": 35.6895,
        "lon": 139.6917,
        "timezone": "Asia/Tokyo",
    },
    "osaka": {
        "name": "Osaka",
        "aliases": ("osaka", "大阪"),
        "lat": 34.6937,
        "lon": 135.5023,
        "timezone": "Asia/Tokyo",
    },
    "kyoto": {
        "name": "Kyoto",
        "aliases": ("kyoto", "京都"),
        "lat": 35.0116,
        "lon": 135.7681,
        "timezone": "Asia/Tokyo",
    },
    "jinan": {
        "name": "Jinan",
        "aliases": ("jinan", "济南", "濟南"),
        "lat": 36.6512,
        "lon": 117.1201,
        "timezone": "Asia/Shanghai",
    },
}


def _weather_city_by_alias(name: str) -> dict[str, object] | None:
    normalized = name.strip().lower()
    if not normalized:
        return None
    for city in _KNOWN_WEATHER_CITIES.values():
        aliases = city.get("aliases") or ()
        if any(normalized == str(alias).lower() for alias in aliases):
            return dict(city)
    return None


def _extract_forecast_days(user_text: str) -> int:
    lower = user_text.lower()
    if re.search(r"三天|3\s*(?:天|days?)|three\s+days?", lower):
        return 3
    if re.search(r"七天|7\s*(?:天|days?)|week|一周", lower):
        return 7
    return 3


def _extract_weather_city_names(user_text: str) -> list[str]:
    lower = user_text.lower()
    names: list[str] = []
    seen: set[str] = set()

    def add(name: str) -> None:
        cleaned = re.sub(
            r"^(请|帮我|麻烦|查询|查一下|查|获取|看看|看一下|给出|一下|当前|今天|未来|最近)+",
            "",
            name.strip(),
        )
        cleaned = re.sub(
            r"(未来|最近)?\s*(三天|七天|[0-9]+\s*天|天气情况|天气预报|天气|天氣|气象|氣象|forecast|weather).*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip(" ，,、;；。.:：")
        cleaned = re.sub(r"(三地|两地|二地|四地|五地|各地)$", "", cleaned).strip(" ，,、;；。.:：")
        known = _weather_city_by_alias(cleaned)
        if known is not None:
            cleaned = str(known["name"])
        if not cleaned:
            return
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            names.append(cleaned)

    for city in _KNOWN_WEATHER_CITIES.values():
        if any(str(alias).lower() in lower or str(alias) in user_text for alias in city.get("aliases", ())):
            add(str(city["name"]))

    cjk_match = re.search(
        r"(?:查询|查一下|查|获取|看看|看一下|给出|请)?([\u4e00-\u9fffA-Za-z\s,，、和与及以及-]{1,80}?)(?:未来|最近|今天|明天|后天|天气|天氣|气象|氣象)",
        user_text,
        re.IGNORECASE,
    )
    if cjk_match:
        raw = cjk_match.group(1)
        for part in re.split(r"、|，|,|/|和|与|及|以及|\band\b", raw):
            add(part)

    english_match = re.search(r"\b([a-z][a-z\s.-]{2,40})\s+(?:weather|forecast)\b", lower)
    if english_match:
        for part in re.split(r",|/|\band\b", english_match.group(1)):
            add(part)

    return names[:6]


def _maybe_build_weather_snapshot(user_text: str) -> SystemMessage | None:
    lower = user_text.lower()
    if not any(token in lower or token in user_text for token in ("weather", "forecast", "天气", "天氣", "氣象")):
        return None

    requested_names = _extract_weather_city_names(user_text)
    if not requested_names:
        return None
    forecast_days = _extract_forecast_days(user_text)

    def describe_weather(code: int | None) -> str:
        if code is None:
            return "unknown"
        if code == 0:
            return "clear"
        if code in {1, 2, 3}:
            return "partly cloudy"
        if code in {45, 48}:
            return "fog"
        if code in {51, 53, 55, 56, 57}:
            return "drizzle"
        if code in {61, 63, 65, 66, 67, 80, 81, 82}:
            return "rain"
        if code in {71, 73, 75, 77, 85, 86}:
            return "snow"
        if code in {95, 96, 99}:
            return "thunderstorm"
        return f"weather code {code}"

    forecasts: list[dict[str, object]] = []
    unresolved: list[str] = []
    try:
        import time
        from concurrent.futures import ThreadPoolExecutor

        import httpx

        def resolve_city(client: httpx.Client, name: str) -> dict[str, object] | None:
            known = _weather_city_by_alias(name)
            if known is not None:
                return known
            response = client.get(
                "https://geocoding-api.open-meteo.com/v1/search",
                params={"name": name, "count": 1, "language": "zh", "format": "json"},
                timeout=8.0,
            )
            response.raise_for_status()
            data = response.json()
            results = data.get("results") or []
            if not results:
                return None
            hit = results[0]
            return {
                "name": hit.get("name") or name,
                "requested_name": name,
                "country": hit.get("country"),
                "admin1": hit.get("admin1"),
                "lat": hit.get("latitude"),
                "lon": hit.get("longitude"),
                "timezone": hit.get("timezone") or "auto",
            }

        def fetch_wttr_forecast(name: str, error: str) -> dict[str, object]:
            wttr_url = f"https://wttr.in/{quote(name)}"
            with httpx.Client(timeout=12.0, follow_redirects=True) as client:
                response = client.get(wttr_url, params={"format": "j1"})
                response.raise_for_status()
                data = response.json()
            days = []
            for item in (data.get("weather") or [])[:forecast_days]:
                hourly = item.get("hourly") or []
                noon = hourly[len(hourly) // 2] if hourly else {}
                description = ""
                desc_values = noon.get("weatherDesc") or []
                if desc_values and isinstance(desc_values[0], dict):
                    description = str(desc_values[0].get("value") or "")
                days.append(
                    {
                        "date": item.get("date"),
                        "condition": description or "unknown",
                        "temperature_max_c": item.get("maxtempC"),
                        "temperature_min_c": item.get("mintempC"),
                        "precipitation_probability_max_percent": noon.get("chanceofrain"),
                    }
                )
            return {
                "city": name,
                "requested_name": name,
                "source": "wttr.in",
                "fallback_from_error": error,
                "days": days,
            }

        def fetch_city_forecast(name: str) -> dict[str, object]:
            try:
                with httpx.Client(timeout=12.0, follow_redirects=True) as client:
                    city = resolve_city(client, name)
                    if city is None or city.get("lat") is None or city.get("lon") is None:
                        unresolved.append(name)
                        return {"city": name, "error": "city_not_found", "days": []}
                    response = None
                    success = False
                    last_error: Exception | None = None
                    for attempt in range(3):
                        try:
                            response = client.get(
                                "https://api.open-meteo.com/v1/forecast",
                                params={
                                    "latitude": city["lat"],
                                    "longitude": city["lon"],
                                    "daily": "weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max",
                                    "timezone": city.get("timezone") or "auto",
                                    "forecast_days": forecast_days,
                                },
                            )
                            response.raise_for_status()
                            success = True
                            break
                        except Exception as exc:
                            last_error = exc
                            if attempt < 2:
                                time.sleep(0.4 * (attempt + 1))
                    if response is None or not success:
                        raise last_error or RuntimeError("Open-Meteo request failed")
                    data = response.json()
            except Exception as exc:
                try:
                    return fetch_wttr_forecast(name, str(exc))
                except Exception as fallback_exc:
                    return {
                        "city": name,
                        "error": str(exc),
                        "fallback_error": str(fallback_exc),
                        "days": [],
                    }

            daily = data.get("daily") or {}
            days = []
            for idx, date in enumerate(daily.get("time") or []):
                codes = daily.get("weather_code") or []
                max_temps = daily.get("temperature_2m_max") or []
                min_temps = daily.get("temperature_2m_min") or []
                rain_probs = daily.get("precipitation_probability_max") or []
                code = codes[idx] if idx < len(codes) else None
                days.append(
                    {
                        "date": date,
                        "condition": describe_weather(code),
                        "temperature_max_c": max_temps[idx] if idx < len(max_temps) else None,
                        "temperature_min_c": min_temps[idx] if idx < len(min_temps) else None,
                        "precipitation_probability_max_percent": rain_probs[idx] if idx < len(rain_probs) else None,
                    }
                )
            return {
                "city": city["name"],
                "requested_name": city.get("requested_name") or name,
                "country": city.get("country"),
                "admin1": city.get("admin1"),
                "timezone": data.get("timezone") or city.get("timezone"),
                "source": "Open-Meteo",
                "days": days,
            }

        max_workers = min(6, len(requested_names))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            forecasts = list(executor.map(fetch_city_forecast, requested_names))

        payload = {
            "source_note": f"Open-Meteo forecast, next {forecast_days} forecast days. City coordinates are resolved server-side.",
            "source": "Open-Meteo",
            "requested_cities": requested_names,
            "unresolved_cities": unresolved,
            "forecasts": forecasts,
        }
    except Exception as exc:
        payload = {"error": str(exc), "forecasts": forecasts}

    return SystemMessage(
        content=(
            "<current_weather_snapshot>\n"
            "The latest user request asks for current/future weather. Use this server-fetched forecast directly. "
            "If the snapshot has an error or missing city, explain that clearly instead of guessing.\n"
            f"{json.dumps(payload, ensure_ascii=False)}\n"
            "</current_weather_snapshot>"
        )
    )
