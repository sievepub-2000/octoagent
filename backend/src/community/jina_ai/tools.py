from langchain.tools import tool

from src.community.jina_ai.jina_client import JinaClient
from src.config import get_app_config
from src.utils.readability import ReadabilityExtractor
from src.utils.url_safety import is_url_safe

readability_extractor = ReadabilityExtractor()


@tool("web_fetch", parse_docstring=True)
def web_fetch_tool(url: str) -> str:
    """Fetch the contents of a web page at a given URL.
    Only fetch EXACT URLs that have been provided directly by the user or have been returned in results from the web_search and web_fetch tools.
    This tool can NOT access content that requires authentication, such as private Google Docs or pages behind login walls.
    Do NOT add www. to URLs that do NOT have them.
    URLs must include the schema: https://example.com is a valid URL while example.com is an invalid URL.

    Args:
        url: The URL to fetch the contents of.
    """
    # SSRF protection
    if not is_url_safe(url):
        return "Error: Access to private/internal network addresses is not allowed."

    jina_client = JinaClient()
    timeout = 10
    config = get_app_config().get_tool_config("web_fetch")
    if config is not None and "timeout" in config.model_extra:
        timeout = config.model_extra.get("timeout")
    html_content = jina_client.crawl(url, return_format="html", timeout=timeout)
    if html_content.startswith("Error:"):
        return (
            f"Web fetch failed for {url}. {html_content}\n"
            "Suggestion: try another source URL or use web_search to gather alternative references."
        )
    article = readability_extractor.extract_article(html_content)
    return article.to_markdown()[:4096]
