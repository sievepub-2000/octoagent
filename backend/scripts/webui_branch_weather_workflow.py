#!/usr/bin/env python3
"""
Playwright automation: Create a branch workflow from OctoAgent WebUI.

Steps:
1. Create 3 agents via WebUI: tokyo-weather, kyoto-weather, hokkaido-weather
2. Create a branch workflow with main agent + 3 sub-agents
3. Run the workflow
4. Monitor until completion
5. Verify results

Usage:
    python scripts/webui_branch_weather_workflow.py
"""

import json
import os
import sys
import time
import urllib.request
from datetime import datetime

from playwright.sync_api import Page, sync_playwright

BASE_URL = os.environ.get("OCTOAGENT_URL", "http://127.0.0.1:19880")
GATEWAY_URL = os.environ.get("GATEWAY_URL", "http://127.0.0.1:19882")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
TIMEOUT = 15_000  # 15s default timeout for actions

os.makedirs(SCREENSHOT_DIR, exist_ok=True)


def screenshot(page: Page, name: str):
    path = os.path.join(SCREENSHOT_DIR, f"{name}.png")
    page.screenshot(path=path, full_page=True)
    print(f"  📸 Screenshot: {path}")
    return path


def wait_for_page_load(page: Page):
    """Wait for Next.js page to fully load."""
    page.wait_for_load_state("networkidle", timeout=20_000)
    time.sleep(1)  # extra settle time for React hydration


def create_agent_via_webui(page: Page, agent_name: str, description: str, soul: str) -> bool:
    """Create an agent through the WebUI new agent page."""
    print(f"\n🤖 Creating agent: {agent_name}")

    # Navigate to new agent page
    page.goto(f"{BASE_URL}/workspace/agents/new", wait_until="networkidle", timeout=30_000)
    wait_for_page_load(page)
    screenshot(page, f"agent_create_{agent_name}_1_loaded")

    # Fill name field - it's the first input with placeholder containing "code-reviewer"
    name_input = page.locator("input[placeholder='code-reviewer']")
    if name_input.count() == 0:
        # Try first input in form
        name_input = page.locator("input").first
    name_input.click()
    name_input.fill(agent_name)
    time.sleep(0.3)

    # Fill description - first textarea
    textareas = page.locator("textarea")
    if textareas.count() >= 1:
        textareas.nth(0).click()
        textareas.nth(0).fill(description)

    # Fill soul (system prompt) - second textarea
    if textareas.count() >= 2:
        textareas.nth(1).click()
        textareas.nth(1).fill(soul)

    screenshot(page, f"agent_create_{agent_name}_2_filled")

    # Click Continue/Create button
    create_btn = page.locator("button").filter(has_text="Continue")
    if create_btn.count() == 0:
        create_btn = page.locator("button").filter(has_text="Create")
    if create_btn.count() == 0:
        create_btn = page.locator("button").filter(has_text="创建")

    create_btn.click()
    time.sleep(3)  # Wait for creation and navigation

    screenshot(page, f"agent_create_{agent_name}_3_created")
    print(f"  ✅ Agent {agent_name} created")
    return True


def create_branch_workflow_via_webui(page: Page) -> str | None:
    """Create a branch workflow through the WebUI wizard."""
    print("\n📋 Creating branch workflow via wizard...")

    # Navigate to workflows page
    page.goto(f"{BASE_URL}/workspace/workflows", wait_until="networkidle", timeout=30_000)
    wait_for_page_load(page)
    screenshot(page, "workflow_01_workflows_page")

    # Click "New Workflow" button
    new_btn = page.locator("button").filter(has_text="New Workflow")
    if new_btn.count() == 0:
        new_btn = page.locator("button").filter(has_text="新建工作流")
    if new_btn.count() == 0:
        new_btn = page.locator("button").filter(has_text="新工作流")
    if new_btn.count() == 0:
        # Try the plus icon button
        new_btn = page.locator("button").filter(has=page.locator("svg"))
        # find the one that's not destructive
        for i in range(new_btn.count()):
            btn = new_btn.nth(i)
            text = btn.inner_text().strip()
            if "Workflow" in text or "工作" in text or "New" in text:
                new_btn = btn
                break

    new_btn.click()
    time.sleep(1)
    screenshot(page, "workflow_02_wizard_task_step")

    # ── Step 1: Task Info ──
    print("  Step 1: Task Info")
    # Fill task name
    name_input = page.locator("div[role='dialog'] input")
    name_input.fill("三地天气分支查询 (3-City Weather Branch)")
    time.sleep(0.3)

    # Fill task goal
    goal_textarea = page.locator("div[role='dialog'] textarea")
    goal_textarea.fill("使用分支任务模式，由主Agent安排三个子Agent分别获取东京(Tokyo)、京都(Kyoto)、北海道(Hokkaido)未来三天的天气情况。每个子Agent负责一个城市的天气查询，最后由主Agent汇总所有结果展示。")

    screenshot(page, "workflow_03_task_filled")

    # Click Next
    next_btn = page.locator("div[role='dialog'] button").filter(has_text="Next")
    if next_btn.count() == 0:
        next_btn = page.locator("div[role='dialog'] button").filter(has_text="下一步")
    next_btn.click()
    time.sleep(0.5)
    screenshot(page, "workflow_04_agent_step")

    # ── Step 2: Agent Mode + Selection ──
    print("  Step 2: Agent Mode (Multi-Agent)")
    # Click "Sub-Agents" / multi-agent mode button
    multi_btn = page.locator("div[role='dialog'] button").filter(has_text="Sub-Agent")
    if multi_btn.count() == 0:
        multi_btn = page.locator("div[role='dialog'] button").filter(has_text="多Agent")
    if multi_btn.count() == 0:
        multi_btn = page.locator("div[role='dialog'] button").filter(has_text="Multi")
    multi_btn.click()
    time.sleep(0.5)

    screenshot(page, "workflow_05_multi_agent_selected")

    # Select sub-agents - click on each agent button in the sub-agents list
    print("  Selecting sub-agents: tokyo-weather, kyoto-weather, hokkaido-weather")
    for agent_name in ["tokyo-weather", "kyoto-weather", "hokkaido-weather"]:
        agent_btn = page.locator("div[role='dialog'] button").filter(has_text=agent_name)
        if agent_btn.count() > 0:
            agent_btn.first.click()
            time.sleep(0.3)
            print(f"    ✅ Selected: {agent_name}")
        else:
            print(f"    ⚠️ Agent not found in list: {agent_name}")

    screenshot(page, "workflow_06_agents_selected")

    # Click Next
    next_btn = page.locator("div[role='dialog'] button").filter(has_text="Next")
    if next_btn.count() == 0:
        next_btn = page.locator("div[role='dialog'] button").filter(has_text="下一步")
    next_btn.click()
    time.sleep(0.5)
    screenshot(page, "workflow_07_topology_step")

    # ── Step 3: Topology → Branch ──
    print("  Step 3: Topology (Branch)")
    branch_btn = page.locator("div[role='dialog'] button").filter(has_text="Branch")
    if branch_btn.count() == 0:
        branch_btn = page.locator("div[role='dialog'] button").filter(has_text="分支")
    branch_btn.click()
    time.sleep(0.3)

    screenshot(page, "workflow_08_branch_selected")

    # Click Next
    next_btn = page.locator("div[role='dialog'] button").filter(has_text="Next")
    if next_btn.count() == 0:
        next_btn = page.locator("div[role='dialog'] button").filter(has_text="下一步")
    next_btn.click()
    time.sleep(0.5)
    screenshot(page, "workflow_09_execution_step")

    # ── Step 4: Execution Mode → Chat (default) ──
    print("  Step 4: Execution Mode (Conversation - default)")
    # Conversation should be selected by default, just verify
    screenshot(page, "workflow_10_execution_mode")

    # Click Create
    create_btn = page.locator("div[role='dialog'] button").filter(has_text="Create")
    if create_btn.count() == 0:
        create_btn = page.locator("div[role='dialog'] button").filter(has_text="创建")
    create_btn.click()
    time.sleep(2)

    screenshot(page, "workflow_11_created")
    print("  ✅ Workflow created!")

    # Get the task_id from the API
    resp = urllib.request.urlopen(f"{GATEWAY_URL}/api/task-workspaces")
    workspaces = json.loads(resp.read().decode())
    ws_list = workspaces if isinstance(workspaces, list) else workspaces.get("workspaces", [])
    # Find the newest one
    for ws in ws_list:
        if "三地天气" in (ws.get("name") or "") or "3-City" in (ws.get("name") or ""):
            task_id = ws["task_id"]
            print(f"  Task ID: {task_id}")
            return task_id

    if ws_list:
        task_id = ws_list[0]["task_id"]
        print(f"  Task ID (first): {task_id}")
        return task_id

    return None


def run_workflow_via_webui(page: Page, task_id: str | None) -> bool:
    """Run the workflow by clicking the Play button in the WebUI."""
    print("\n▶️ Running workflow...")

    # Refresh workflows page
    page.goto(f"{BASE_URL}/workspace/workflows", wait_until="networkidle", timeout=30_000)
    wait_for_page_load(page)

    screenshot(page, "workflow_12_before_run")

    # Find the play button (green) for the workflow card with "三地天气" or "3-City"
    # The play button is a small icon button with PlayIcon inside
    play_btns = page.locator("button[title='Run'], button[title='运行']")
    if play_btns.count() == 0:
        # Look for green play icons - they have text-green-600 class
        play_btns = page.locator("button.text-green-600")
    if play_btns.count() == 0:
        # Try any visible play button
        play_btns = page.locator("button").filter(has=page.locator("svg")).filter(has_text="")

    # Click the first available play button (should be our newest workflow)
    if play_btns.count() > 0:
        play_btns.first.click()
        print("  ▶️ Clicked Run button")
        time.sleep(2)
    else:
        print("  ⚠️ No Run button found, trying API fallback...")
        try:
            req = urllib.request.Request(
                f"{GATEWAY_URL}/api/task-workspaces/{task_id}/run",
                data=json.dumps({"auto_compile": True, "auto_iterate": True, "max_iterations": 3}).encode(),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req)
            print("  ✅ Started via API")
        except Exception as e:
            print(f"  ❌ Failed to start: {e}")
            return False

    screenshot(page, "workflow_13_running")
    return True


def wait_for_completion(page: Page, task_id: str, max_wait_seconds: int = 420) -> dict:
    """Poll the API until the workflow completes or times out."""
    print(f"\n⏳ Waiting for workflow completion (max {max_wait_seconds}s)...")
    start = time.time()
    last_status = ""

    while time.time() - start < max_wait_seconds:
        try:
            resp = urllib.request.urlopen(f"{GATEWAY_URL}/api/task-workspaces/{task_id}")
            data = json.loads(resp.read().decode())
            status = data.get("status", "unknown")

            if status != last_status:
                elapsed = time.time() - start
                print(f"  [{elapsed:.0f}s] Status: {status}")
                last_status = status

                # Take screenshot on status change
                page.reload(wait_until="networkidle", timeout=15_000)
                time.sleep(1)
                screenshot(page, f"workflow_status_{status}_{int(elapsed)}")

            if status in ("completed", "failed", "terminated"):
                return data

        except Exception as e:
            print(f"  ⚠️ Poll error: {e}")

        time.sleep(10)

    print(f"  ⏰ Timed out after {max_wait_seconds}s")
    return {"status": "timeout"}


def verify_results(page: Page, task_id: str) -> dict:
    """Verify the workflow results."""
    print("\n🔍 Verifying results...")

    resp = urllib.request.urlopen(f"{GATEWAY_URL}/api/task-workspaces/{task_id}")
    data = json.loads(resp.read().decode())

    result = {
        "task_id": task_id,
        "status": data.get("status"),
        "name": data.get("name"),
        "mode": data.get("mode"),
        "agents": [],
        "summary": data.get("summary", ""),
        "has_weather_data": False,
        "cities_found": [],
    }

    # Check agents
    for agent in data.get("agents", []):
        result["agents"].append(
            {
                "name": agent.get("name"),
                "status": agent.get("status"),
                "role": agent.get("role"),
            }
        )

    # Check if weather data is in summary or output
    summary = data.get("summary") or ""
    metadata = data.get("metadata") or {}
    output = metadata.get("last_output") or summary

    cities = {"tokyo": "東京/Tokyo", "kyoto": "京都/Kyoto", "hokkaido": "北海道/Hokkaido"}
    for city_key, city_label in cities.items():
        if city_key.lower() in output.lower() or city_label.split("/")[0] in output:
            result["cities_found"].append(city_label)
            result["has_weather_data"] = True

    # Navigate to workflow detail page
    page.goto(f"{BASE_URL}/workspace/workflows/{task_id}", wait_until="networkidle", timeout=30_000)
    wait_for_page_load(page)
    screenshot(page, "workflow_14_detail_page")

    # Also check workflows list view
    page.goto(f"{BASE_URL}/workspace/workflows", wait_until="networkidle", timeout=30_000)
    wait_for_page_load(page)
    screenshot(page, "workflow_15_final_list")

    return result


def main():
    print("=" * 60)
    print("OctoAgent Branch Weather Workflow - WebUI Automation")
    print(f"Time: {datetime.now().isoformat()}")
    print(f"WebUI: {BASE_URL}")
    print(f"Gateway: {GATEWAY_URL}")
    print("=" * 60)

    # Check services
    try:
        urllib.request.urlopen(f"{BASE_URL}/workspace/workflows", timeout=5)
        print("✅ Frontend reachable")
    except Exception as e:
        print(f"❌ Frontend unreachable: {e}")
        sys.exit(1)

    try:
        resp = urllib.request.urlopen(f"{GATEWAY_URL}/api/models", timeout=5)
        models = json.loads(resp.read().decode())
        model_count = len(models.get("models", models) if isinstance(models, dict) else models)
        print(f"✅ Gateway reachable (models: {model_count})")
    except Exception as e:
        print(f"❌ Gateway unreachable: {e}")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            locale="en-US",
        )
        page = context.new_page()
        page.set_default_timeout(TIMEOUT)

        try:
            # ── Phase 1: Create 3 weather agents ──
            agents_config = [
                (
                    "tokyo-weather",
                    "Weather researcher for Tokyo, Japan",
                    "You are a weather research agent specializing in Tokyo (東京). "
                    "When asked about weather, use the web_search tool to find current weather forecasts for Tokyo, Japan. "
                    "Always report: date, weather condition, max/min temperature (°C), precipitation probability. "
                    "Provide data for the next 3 days.",
                ),
                (
                    "kyoto-weather",
                    "Weather researcher for Kyoto, Japan",
                    "You are a weather research agent specializing in Kyoto (京都). "
                    "When asked about weather, use the web_search tool to find current weather forecasts for Kyoto, Japan. "
                    "Always report: date, weather condition, max/min temperature (°C), precipitation probability. "
                    "Provide data for the next 3 days.",
                ),
                (
                    "hokkaido-weather",
                    "Weather researcher for Hokkaido, Japan",
                    "You are a weather research agent specializing in Hokkaido (北海道). "
                    "When asked about weather, use the web_search tool to find current weather forecasts for Hokkaido (Sapporo area), Japan. "
                    "Always report: date, weather condition, max/min temperature (°C), precipitation probability. "
                    "Provide data for the next 3 days.",
                ),
            ]

            for name, desc, soul in agents_config:
                # Check if agent already exists
                try:
                    resp = urllib.request.urlopen(f"{GATEWAY_URL}/api/agents")
                    existing = json.loads(resp.read().decode())
                    agent_names = [a["name"] for a in existing.get("agents", existing if isinstance(existing, list) else [])]
                    if name in agent_names:
                        print(f"  ⏭️ Agent {name} already exists, skipping")
                        continue
                except Exception:
                    pass

                create_agent_via_webui(page, name, desc, soul)

            # Verify agents exist
            resp = urllib.request.urlopen(f"{GATEWAY_URL}/api/agents")
            agents = json.loads(resp.read().decode())
            agent_names = [a["name"] for a in agents.get("agents", agents if isinstance(agents, list) else [])]
            print(f"\n📋 Agents available: {agent_names}")
            for required in ["tokyo-weather", "kyoto-weather", "hokkaido-weather"]:
                if required not in agent_names:
                    print(f"  ❌ Missing agent: {required}")

            # ── Phase 2: Create branch workflow ──
            task_id = create_branch_workflow_via_webui(page)
            if not task_id:
                print("❌ Failed to create workflow")
                screenshot(page, "workflow_ERROR_no_task_id")
                sys.exit(1)

            # ── Phase 3: Run workflow ──
            started = run_workflow_via_webui(page, task_id)
            if not started:
                print("❌ Failed to start workflow")
                sys.exit(1)

            # ── Phase 4: Wait for completion ──
            wait_for_completion(page, task_id, max_wait_seconds=420)

            # ── Phase 5: Verify results ──
            verification = verify_results(page, task_id)

            # ── Report ──
            print("\n" + "=" * 60)
            print("📊 EXECUTION REPORT")
            print("=" * 60)
            print(f"Task ID: {verification['task_id']}")
            print(f"Name: {verification['name']}")
            print(f"Status: {verification['status']}")
            print(f"Mode: {verification['mode']}")
            print(f"Agents: {len(verification['agents'])}")
            for ag in verification["agents"]:
                print(f"  - {ag['name']} ({ag['role']}): {ag['status']}")
            print(f"Weather data found: {verification['has_weather_data']}")
            print(f"Cities covered: {verification['cities_found']}")
            print(f"\nSummary preview:\n{verification['summary'][:800]}")
            print("=" * 60)

            # Write result to file
            result_path = os.path.join(SCREENSHOT_DIR, "execution_result.json")
            with open(result_path, "w") as f:
                json.dump(verification, f, indent=2, ensure_ascii=False)
            print(f"\nFull result saved to: {result_path}")

        except Exception as e:
            screenshot(page, "workflow_EXCEPTION")
            print(f"\n❌ Exception: {e}")
            import traceback

            traceback.print_exc()
            sys.exit(1)
        finally:
            browser.close()

    print("\n✅ Automation complete!")


if __name__ == "__main__":
    main()
