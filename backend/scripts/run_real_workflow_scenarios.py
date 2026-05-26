#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, expect, sync_playwright

BASE_URL = os.environ.get("OCTO_WORKFLOW_UI_BASE_URL", "http://127.0.0.1:19880")
GATEWAY_URL = os.environ.get("OCTO_WORKFLOW_GATEWAY_URL", "http://127.0.0.1:19882")
RUNTIME_PROVIDER = os.environ.get("OCTO_WORKFLOW_RUNTIME_PROVIDER", "crewai")
RUNTIME_PROVIDER_LABEL = "CrewAI" if RUNTIME_PROVIDER == "crewai" else "LangGraph"
SCREENSHOT_DIR = Path(__file__).resolve().parent.parent / "screenshots" / "real-workflow-validation"
REPORT_PATH = SCREENSHOT_DIR / "workflow_validation_report.json"
TIMEOUT_SECONDS = int(os.environ.get("OCTO_WORKFLOW_SCENARIO_TIMEOUT", "600"))

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def api_request(
    path: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout: int = 60,
) -> Any:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    last_error: Exception | None = None
    for attempt in range(5):
        request = urllib.request.Request(
            f"{GATEWAY_URL}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body) if body else None
        except urllib.error.HTTPError:
            raise
        except (urllib.error.URLError, ConnectionResetError, TimeoutError) as exc:
            last_error = exc
            if attempt == 4:
                raise
            time.sleep(min(2 * (attempt + 1), 8))

    if last_error is not None:
        raise last_error

    raise RuntimeError(f"request failed without a captured exception: {path}")


def load_text(url: str, timeout: int = 60) -> str:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def screenshot(page: Page, name: str) -> str:
    path = SCREENSHOT_DIR / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    return str(path)


@dataclass
class ScenarioDefinition:
    key: str
    title: str
    mode: str
    goal: str
    primary_agent: str
    sub_agents: list[str]
    expected_keywords: list[str]
    required_agents: int
    requires_research: bool = True


AGENT_DEFINITIONS: dict[str, dict[str, str]] = {
    "three-city-weather-analyst": {
        "description": "Single-agent researcher for Kyoto, Osaka, and Tokyo weather",
        "soul": (
            "You are a weather research agent specializing in Kyoto, Osaka, and Tokyo, Japan. "
            "Always use weather_forecast first for weather tasks. "
            "Only use web_search or web_fetch if weather_forecast fails or lacks required detail. "
            "Return the next 3 days for all three cities with date, condition, max/min temperature in Celsius, "
            "precipitation chance, and at least one source link per city."
        ),
    },
    "tokyo-weather": {
        "description": "Weather researcher for Tokyo, Japan",
        "soul": (
            "You are a weather research agent specializing in Tokyo, Japan. "
            "Always use weather_forecast first for weather tasks. "
            "Only use web_search or web_fetch if weather_forecast fails or lacks required detail. "
            "Return the next 3 days with date, condition, max/min temperature in Celsius, "
            "precipitation chance, and at least one source link."
        ),
    },
    "osaka-weather": {
        "description": "Weather researcher for Osaka, Japan",
        "soul": (
            "You are a weather research agent specializing in Osaka, Japan. "
            "Always use weather_forecast first for weather tasks. "
            "Only use web_search or web_fetch if weather_forecast fails or lacks required detail. "
            "Return the next 3 days with date, condition, max/min temperature in Celsius, "
            "precipitation chance, and at least one source link."
        ),
    },
    "kyoto-weather": {
        "description": "Weather researcher for Kyoto, Japan",
        "soul": (
            "You are a weather research agent specializing in Kyoto, Japan. "
            "Always use weather_forecast first for weather tasks. "
            "Only use web_search or web_fetch if weather_forecast fails or lacks required detail. "
            "Return the next 3 days with date, condition, max/min temperature in Celsius, "
            "precipitation chance, and at least one source link."
        ),
    },
    "weather-coordinator": {
        "description": "Lead coordinator for multi-city weather workflows",
        "soul": ("You are a coordinator agent for weather workflows. You must decompose tasks, rely on sub-agents for each city, and synthesize only from their real outputs. If evidence is missing, say so clearly instead of guessing."),
    },
    "speed-orchestrator": {
        "description": "Lead coordinator for llama.cpp and Gemma throughput investigations",
        "soul": ("You are the lead coordinator for inference-performance investigations. You must assign sub-agents, compare their findings, and deliver a concrete optimization plan only from their real outputs."),
    },
    "llamacpp-throughput-analyst": {
        "description": "Research agent for llama.cpp throughput and latency tuning",
        "soul": (
            "You analyze llama.cpp performance. "
            "Use web_search or web_fetch to find current public guidance on GPU offload, batching, flash attention, kv cache, threads, quantization, and context tuning. "
            "Return evidence-backed recommendations with sources."
        ),
    },
    "gemma4-serving-analyst": {
        "description": "Research agent for Gemma deployment and serving optimization",
        "soul": (
            "You analyze Gemma model serving performance. "
            "Use web_search or web_fetch to find current public guidance on Gemma 4 style dense models, prompt formatting, context length, quantization tradeoffs, and serving throughput. "
            "Return evidence-backed recommendations with sources."
        ),
    },
}


SCENARIOS: list[ScenarioDefinition] = [
    ScenarioDefinition(
        key="single_three_city_weather",
        title="Single Chain Kyoto Osaka Tokyo Weather",
        mode="single",
        goal=("Use the latest public web information to report Kyoto, Osaka, and Tokyo weather for the next 3 days. Include date, condition, max/min temperature in Celsius, precipitation probability, and source URLs for each city."),
        primary_agent="three-city-weather-analyst",
        sub_agents=[],
        expected_keywords=["kyoto", "osaka", "tokyo", "http"],
        required_agents=1,
    ),
    ScenarioDefinition(
        key="branch_three_city_weather",
        title="Branch Tokyo Osaka Kyoto Weather",
        mode="branch",
        goal=("The coordinator must ask three sub-agents to independently gather the latest public 3-day weather forecasts for Tokyo, Osaka, and Kyoto, then synthesize the combined result with source URLs."),
        primary_agent="weather-coordinator",
        sub_agents=["tokyo-weather", "osaka-weather", "kyoto-weather"],
        expected_keywords=["tokyo", "osaka", "kyoto", "http"],
        required_agents=4,
    ),
    ScenarioDefinition(
        key="group_three_city_weather",
        title="Group Tokyo Osaka Kyoto Weather",
        mode="group",
        goal=(
            "The coordinator must ask three specialist city agents to discuss and synthesize the latest public 3-day weather forecasts for Tokyo, Osaka, and Kyoto. "
            "The final answer must include each city, date, condition, max/min temperature in Celsius, precipitation probability, and source URLs."
        ),
        primary_agent="weather-coordinator",
        sub_agents=["tokyo-weather", "osaka-weather", "kyoto-weather"],
        expected_keywords=["tokyo", "osaka", "kyoto", "http"],
        required_agents=4,
    ),
]


FALLBACK_MARKERS = [
    "Live runtime chat handoff is not wired yet",
    "Execution failed:",
    "Tool fallback executed by server",
    "Validation note: expected at least one web/tool call",
    "Execution failed: multi-agent workflow did not return a valid LangGraph result.",
]


def ensure_connectivity() -> None:
    checks = [
        (f"{BASE_URL}/workspace/workflows", "webui"),
        (f"{GATEWAY_URL}/api/models", "gateway"),
    ]
    for url, label in checks:
        try:
            with urllib.request.urlopen(url, timeout=15) as response:
                if response.status >= 400:
                    raise RuntimeError(f"{label} status={response.status}")
        except Exception as exc:
            raise RuntimeError(f"{label} unavailable at {url}: {exc}") from exc


def list_agents() -> dict[str, dict[str, Any]]:
    payload = api_request("/api/agents")
    agents = payload.get("agents", []) if isinstance(payload, dict) else []
    return {str(agent["name"]): agent for agent in agents}


def ensure_agents() -> None:
    existing = list_agents()
    for name, definition in AGENT_DEFINITIONS.items():
        if name in existing:
            continue
        api_request(
            "/api/agents",
            method="POST",
            payload={
                "name": name,
                "description": definition["description"],
                "soul": definition["soul"],
            },
        )


def delete_existing_scenario_workspaces() -> None:
    payload = api_request("/api/task-workspaces")
    workspaces = payload.get("workspaces", []) if isinstance(payload, dict) else []
    for workspace in workspaces:
        name = str(workspace.get("name") or "")
        if name.startswith("Real Workflow Validation :: "):
            try:
                api_request(f"/api/task-workspaces/{workspace['task_id']}", method="DELETE")
            except urllib.error.HTTPError as exc:
                if exc.code != 404:
                    raise


def create_workspace(definition: ScenarioDefinition) -> dict[str, Any]:
    summary = {
        "topology": "chain" if definition.mode == "single" else ("branch" if definition.mode == "branch" else "swarm"),
        "runMode": "chat",
        "primaryAgent": definition.primary_agent,
        "subAgents": definition.sub_agents or None,
    }
    payload = {
        "name": f"Real Workflow Validation :: {definition.title}",
        "goal": definition.goal,
        "mode": definition.mode,
        "agent_runtime_provider": RUNTIME_PROVIDER,
        "summary": json.dumps(summary, ensure_ascii=False),
        "expected_keywords": definition.expected_keywords,
        "timeout_seconds": TIMEOUT_SECONDS,
        "max_turns": 40,
    }
    return api_request("/api/task-workspaces", method="POST", payload=payload)


def list_workspaces_payload() -> list[dict[str, Any]]:
    payload = api_request("/api/task-workspaces")
    return payload.get("workspaces", []) if isinstance(payload, dict) else []


def wait_for_workspace_by_name(name: str, timeout_seconds: int = 30) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        for workspace in list_workspaces_payload():
            if str(workspace.get("name") or "") == name:
                return workspace
        time.sleep(1)
    raise TimeoutError(f"workspace '{name}' was not created within {timeout_seconds}s")


def update_workspace_definition(task_id: str, definition: ScenarioDefinition) -> None:
    summary = {
        "topology": "chain" if definition.mode == "single" else ("branch" if definition.mode == "branch" else "swarm"),
        "runMode": "chat",
        "primaryAgent": definition.primary_agent,
        "subAgents": definition.sub_agents or None,
    }
    api_request(
        f"/api/task-workspaces/{task_id}",
        method="PUT",
        payload={
            "name": f"Real Workflow Validation :: {definition.title}",
            "top_bar_label": f"Real Workflow Validation :: {definition.title}",
            "goal": definition.goal,
            "summary": json.dumps(summary, ensure_ascii=False),
            "agent_runtime_provider": RUNTIME_PROVIDER,
        },
    )


def open_create_dialog(page: Page) -> None:
    page.goto(f"{BASE_URL}/workspace/workflows", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)
    page.get_by_role(
        "button",
        name=re.compile(r"^(New Workflow|Create Workflow|新建工作流|创建工作流)$", re.I),
    ).first.click()
    expect(page.get_by_role("dialog")).to_be_visible(timeout=10_000)


def create_workspace_via_webui(page: Page, definition: ScenarioDefinition) -> dict[str, Any]:
    workflow_name = f"Real Workflow Validation :: {definition.title}"
    open_create_dialog(page)
    dialog = page.get_by_role("dialog")

    dialog.locator("input").first.fill(workflow_name)
    dialog.locator("textarea").first.fill(definition.goal)
    dialog.get_by_role("button", name=re.compile(r"^(Next|下一步)$", re.I)).click()

    if definition.mode != "single":
        dialog.get_by_role(
            "button",
            name=re.compile(r"^(Multi-Agent|Multi Agent|Sub-Agent|Sub-Agents|多Agent|多智能体|子智能体|子智能體)$", re.I),
        ).click()
        dialog.get_by_role("combobox").first.click()
        page.get_by_role("option", name=re.compile(rf"^{re.escape(definition.primary_agent)}(?:\s|$)", re.I)).click()
        for sub_agent in definition.sub_agents[: max(1, min(len(definition.sub_agents), 3))]:
            dialog.get_by_role("button", name=re.compile(rf"^{re.escape(sub_agent)}$", re.I)).click()

    dialog.get_by_role("button", name=re.compile(r"^(Next|下一步)$", re.I)).click()

    if definition.mode != "single":
        topology_pattern = re.compile(r"Branch|分支|ブランチ|브랜치", re.I) if definition.mode == "branch" else re.compile(r"Swarm|群组|群組|群集|スウォーム|스웜", re.I)
        expect(dialog.get_by_role("button", name=topology_pattern)).to_be_visible(timeout=10_000)
        dialog.get_by_role("button", name=topology_pattern).click()
        dialog.get_by_role("button", name=re.compile(r"^(Next|下一步)$", re.I)).click()

    dialog = page.get_by_role("dialog").last
    expect(dialog.get_by_text("Runtime provider", exact=False)).to_be_visible(timeout=10_000)
    dialog.get_by_role("combobox").last.click()
    page.get_by_role("option", name=re.compile(rf"^{re.escape(RUNTIME_PROVIDER_LABEL)}$", re.I)).click()

    dialog.get_by_role("button", name=re.compile(r"^(Create|创建)$", re.I)).click()
    expect(dialog).not_to_be_visible(timeout=20_000)

    workspace = wait_for_workspace_by_name(workflow_name)
    update_workspace_definition(workspace["task_id"], definition)
    return api_request(f"/api/task-workspaces/{workspace['task_id']}")


def configure_workspace_agents_model(task_id: str) -> None:
    """Set model_name on all agents in the workspace to force use of the test model."""
    model_name = os.environ.get("OCTO_TEST_MODEL", "nemotron-3-super-free")
    agents_payload = api_request(f"/api/task-workspaces/{task_id}/agents")
    for agent in agents_payload.get("agents", []):
        agent_id = agent["agent_id"]
        try:
            api_request(
                f"/api/task-workspaces/{task_id}/agents/{agent_id}",
                method="PUT",
                payload={"model_name": model_name},
            )
        except Exception:
            pass  # non-fatal; default model will be used


def run_workspace(task_id: str, mode: str) -> None:
    api_request(
        f"/api/task-workspaces/{task_id}/run",
        method="POST",
        payload={
            "auto_compile": True,
            "auto_iterate": True,
            "max_iterations": 3 if mode != "single" else 1,
        },
        timeout=120,
    )


def run_workspace_via_webui(page: Page, task_id: str) -> None:
    page.goto(f"{BASE_URL}/workspace/workflows/{task_id}", wait_until="domcontentloaded", timeout=60_000)
    expect(page.get_by_test_id("task-action-run")).to_be_visible(timeout=15_000)
    page.get_by_test_id("task-action-run").click()
    page.wait_for_timeout(2000)


def poll_workspace(task_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    request_timeout = max(120, min(timeout_seconds, 600))
    last_status = None
    while time.time() < deadline:
        workspace = api_request(f"/api/task-workspaces/{task_id}", timeout=request_timeout)
        status = workspace.get("status")
        if status != last_status:
            print(f"[{now_iso()}] {task_id} -> {status}")
            last_status = status
        if status in {"completed", "failed", "terminated"}:
            return workspace
        time.sleep(5)
    raise TimeoutError(f"task {task_id} did not finish within {timeout_seconds}s")


def collect_workspace_evidence(task_id: str) -> dict[str, Any]:
    workspace = api_request(f"/api/task-workspaces/{task_id}")
    cards = api_request(f"/api/task-workspaces/{task_id}/cards")
    runtime = api_request(f"/api/task-workspaces/{task_id}/studio-runtime")
    run_log = api_request(f"/api/task-workspaces/{task_id}/run-log")
    result = api_request(f"/api/task-workspaces/{task_id}/result")
    artifacts = api_request(f"/api/task-workspaces/{task_id}/artifacts")
    agents_payload = api_request(f"/api/task-workspaces/{task_id}/agents")
    agent_messages: dict[str, Any] = {}
    for agent in agents_payload.get("agents", []):
        agent_messages[agent["name"]] = api_request(f"/api/task-workspaces/{task_id}/agents/{agent['agent_id']}/messages")
    return {
        "workspace": workspace,
        "cards": cards,
        "runtime": runtime,
        "run_log": run_log,
        "result": result,
        "artifacts": artifacts,
        "agents": agents_payload,
        "agent_messages": agent_messages,
    }


def open_and_capture_ui(page: Page, task_id: str, scenario_key: str) -> dict[str, str]:
    captures: dict[str, str] = {}
    page.goto(f"{BASE_URL}/workspace/workflows", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(1500)
    captures["workflow_list"] = screenshot(page, f"{scenario_key}_list")
    page.goto(f"{BASE_URL}/workspace/workflows/{task_id}?tab=cards", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2000)
    expect(page.get_by_test_id("workflow-result-main-panel")).to_be_visible(timeout=15_000)
    expect(page.get_by_test_id("workflow-runtime-sidebar")).to_be_visible(timeout=15_000)
    captures["cards_tab"] = screenshot(page, f"{scenario_key}_cards")
    page.goto(f"{BASE_URL}/workspace/workflows/{task_id}?tab=agents", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2000)
    captures["agents_tab"] = screenshot(page, f"{scenario_key}_agents")
    page.goto(f"{BASE_URL}/workspace/workflows/{task_id}?tab=brain", wait_until="domcontentloaded", timeout=60_000)
    page.wait_for_timeout(2000)
    captures["brain_tab"] = screenshot(page, f"{scenario_key}_brain")
    return captures


def find_fallback_markers(text: str) -> list[str]:
    lower_text = text.lower()
    return [marker for marker in FALLBACK_MARKERS if marker.lower() in lower_text]


def flatten_messages(agent_messages: dict[str, Any]) -> list[dict[str, str]]:
    flattened: list[dict[str, str]] = []
    for agent_name, payload in agent_messages.items():
        for message in payload.get("messages", []):
            flattened.append(
                {
                    "agent": agent_name,
                    "role": str(message.get("role") or ""),
                    "content": str(message.get("content") or ""),
                }
            )
    return flattened


def validate_scenario(definition: ScenarioDefinition, evidence: dict[str, Any]) -> dict[str, Any]:
    workspace = evidence["workspace"]
    runtime = evidence["runtime"]
    result_content = str(evidence["result"].get("result_content") or "")
    run_log_content = str(evidence["run_log"].get("run_log") or "")
    flattened = flatten_messages(evidence["agent_messages"])
    assistant_messages = [message for message in flattened if message["role"] == "assistant"]
    non_system_assistants = [message for message in assistant_messages if "initialized for task workspace orchestration" not in message["content"]]
    fallback_hits = find_fallback_markers(result_content + "\n" + run_log_content + "\n" + "\n".join(m["content"] for m in assistant_messages))
    runtime_agents = runtime.get("agents", []) if isinstance(runtime, dict) else []
    query_session_agents = [item for item in runtime_agents if item.get("query_session_id")]
    runtime_session_agents = [item for item in runtime_agents if item.get("runtime_session_id")]
    missing_keywords = [keyword for keyword in definition.expected_keywords if keyword.lower() not in result_content.lower()]
    agent_names = [agent.get("name") for agent in evidence["agents"].get("agents", [])]
    incomplete_agents = [agent.get("name") for agent in evidence["agents"].get("agents", []) if agent.get("status") not in {"completed", "running"}]
    pass_checks = {
        "workspace_completed": workspace.get("status") == "completed",
        "agent_count_ok": len(agent_names) >= definition.required_agents,
        "query_sessions_present": len(query_session_agents) >= definition.required_agents,
        "runtime_sessions_present": len(runtime_session_agents) >= definition.required_agents,
        "assistant_outputs_present": len(non_system_assistants) >= definition.required_agents,
        "no_fallback_markers": len(fallback_hits) == 0,
        "keywords_present": len(missing_keywords) == 0,
        "all_agents_completed": len(incomplete_agents) == 0,
    }
    return {
        "status": "passed" if all(pass_checks.values()) else "failed",
        "checks": pass_checks,
        "missing_keywords": missing_keywords,
        "fallback_hits": fallback_hits,
        "agent_names": agent_names,
        "incomplete_agents": incomplete_agents,
        "query_session_agents": len(query_session_agents),
        "runtime_session_agents": len(runtime_session_agents),
        "assistant_message_count": len(non_system_assistants),
        "result_preview": result_content[:4000],
    }


def run_scenario(page: Page, definition: ScenarioDefinition) -> dict[str, Any]:
    workspace = create_workspace_via_webui(page, definition)
    task_id = workspace["task_id"]
    print(f"[{now_iso()}] created {definition.key}: {task_id}")
    configure_workspace_agents_model(task_id)
    run_workspace_via_webui(page, task_id)
    final_workspace = poll_workspace(task_id, TIMEOUT_SECONDS)
    evidence = collect_workspace_evidence(task_id)
    captures = open_and_capture_ui(page, task_id, definition.key)
    validation = validate_scenario(definition, evidence)
    return {
        "scenario": definition.key,
        "title": definition.title,
        "task_id": task_id,
        "final_status": final_workspace.get("status"),
        "workspace_name": final_workspace.get("name"),
        "captures": captures,
        "validation": validation,
        "evidence": evidence,
    }


def main() -> int:
    ensure_connectivity()
    ensure_agents()
    delete_existing_scenario_workspaces()

    report: dict[str, Any] = {
        "generated_at": now_iso(),
        "base_url": BASE_URL,
        "gateway_url": GATEWAY_URL,
        "scenarios": [],
    }

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1600, "height": 1200}, locale="en-US")
        try:
            run_only = os.environ.get("OCTO_RUN_SCENARIOS", "").strip()
            run_only_keys = {k.strip() for k in run_only.split(",") if k.strip()} if run_only else None
            for definition in SCENARIOS:
                if run_only_keys and definition.key not in run_only_keys:
                    print(f"[skip] {definition.key} (not in OCTO_RUN_SCENARIOS)")
                    continue
                scenario_report = run_scenario(page, definition)
                report["scenarios"].append(scenario_report)
        finally:
            browser.close()

    report["overall_status"] = "passed" if all(item["validation"]["status"] == "passed" for item in report["scenarios"]) else "failed"
    REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"overall_status": report["overall_status"], "report": str(REPORT_PATH)}, ensure_ascii=False))
    return 0 if report["overall_status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
