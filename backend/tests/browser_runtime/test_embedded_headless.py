from src.tools.sandbox.browser.contracts import (
    BrowserActionContract,
    BrowserActionExecutionRequest,
    BrowserExecutionSession,
)
from src.tools.sandbox.browser.execution import BrowserSessionExecutionEngine
from src.tools.sandbox.browser.policy import BrowserSessionPolicy


class FakeHeadlessProvider:
    enabled = True
    engine = "patchright"

    def fetch_page(self, target: str):
        return {
            "final_url": target,
            "title": "Example",
            "status_code": 200,
            "content_length": 42,
            "available_targets": [f"{target.rstrip('/')}/next"],
            "available_inputs": ["q"],
        }

    def screenshot(self, session, target: str) -> str:
        return f"/tmp/{session.session_id}.png"

    def evaluate(self, target: str, script: str) -> str:
        return "ok"


def test_browser_runtime_uses_embedded_headless_for_open(monkeypatch):
    monkeypatch.setattr("src.tools.sandbox.browser.execution.EmbeddedHeadlessProvider", lambda: FakeHeadlessProvider())
    engine = BrowserSessionExecutionEngine(policy=BrowserSessionPolicy())
    session = BrowserExecutionSession(
        session_id="browser-test",
        provider="agent_browser",
        target="https://example.com",
        planned_actions=[BrowserActionContract(action_id="open", kind="open", target="https://example.com")],
    )

    result = engine.execute_next_action(
        session,
        BrowserActionExecutionRequest(),
        executed_at="2026-05-20T00:00:00+00:00",
        fetch_page=engine.fetch_page,
    )

    assert result.status == "completed"
    assert result.page_title == "Example"
    assert "headless browser runtime" in result.detail
    assert session.available_inputs == ["q"]


def test_browser_runtime_screenshot_returns_artifact(monkeypatch):
    monkeypatch.setattr("src.tools.sandbox.browser.execution.EmbeddedHeadlessProvider", lambda: FakeHeadlessProvider())
    engine = BrowserSessionExecutionEngine(policy=BrowserSessionPolicy())
    session = BrowserExecutionSession(
        session_id="browser-shot",
        provider="agent_browser",
        target="https://example.com",
        current_url="https://example.com",
        planned_actions=[BrowserActionContract(action_id="shot", kind="screenshot")],
    )

    result = engine.execute_next_action(
        session,
        BrowserActionExecutionRequest(),
        executed_at="2026-05-20T00:00:00+00:00",
        fetch_page=engine.fetch_page,
    )

    assert result.status == "completed"
    assert result.artifact_path == "/tmp/browser-shot.png"
    assert session.latest_artifact_path == "/tmp/browser-shot.png"
