from src.tools.software_interfaces.catalog import get_software_interface, list_software_interfaces, summarize_categories


def test_composio_catalog_contains_expected_core_interfaces():
    interfaces = list_software_interfaces()

    assert len(interfaces) >= 100
    assert get_software_interface("gmail") is not None
    assert get_software_interface("notion") is not None
    assert get_software_interface("slack") is not None


def test_composio_catalog_has_logical_categories():
    categories = {item["id"]: item["count"] for item in summarize_categories()}

    assert categories["communication"] > 0
    assert categories["mail_calendar"] > 0
    assert categories["docs_storage"] > 0
    assert categories["development"] > 0
