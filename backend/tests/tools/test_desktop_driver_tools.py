import json

from src.tools.builtins.desktop_driver_tools import desktop_driver_status_tool


def test_desktop_driver_status_reports_structured_payload():
    payload = json.loads(desktop_driver_status_tool.invoke({}))

    assert "available" in payload
    assert "driver" in payload
    assert "display_available" in payload
