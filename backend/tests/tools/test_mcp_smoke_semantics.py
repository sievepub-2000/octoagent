from src.tools.mcp.smoke import _semantic_failure


def test_semantic_failure_detects_json_wrapped_transport_success() -> None:
    output = [{"type": "text", "text": '{"exit_code": 125, "ok": false, "stderr": "bad flag"}'}]

    assert _semantic_failure(output) == "bad flag"


def test_semantic_failure_accepts_successful_json_tool_result() -> None:
    output = [{"type": "text", "text": '{"exit_code": 0, "ok": true, "stdout": "Docker Compose v2"}'}]

    assert _semantic_failure(output) is None
