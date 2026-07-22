import json

from agent.tool_decorator import tool

from crawlers import WikipediaPage


@tool
def wiki_fetch_page(title_or_url: str) -> str:
    """Fetch summary and categories for a Wikipedia page by title or URL.

    Args:
        title_or_url: Wikipedia page title (e.g. 'Coffee') or full URL.

    Returns:
        JSON string with title, description, url, summary, and categories.
    """
    if title_or_url.startswith("http"):
        page = WikipediaPage(url=title_or_url)
    else:
        page = WikipediaPage(title=title_or_url)

    data = page.fetch_all()
    return json.dumps(data, indent=2, default=str)


@tool
def wiki_search_pages(keyword: str, limit: int = 10) -> str:
    """Search Wikipedia pages by keyword.

    Args:
        keyword: Search query.
        limit: Maximum number of results to return (default 10).

    Returns:
        JSON string list of search result records (titles, snippets, etc.).
    """
    results = WikipediaPage.search(keyword, limit=limit)
    return json.dumps(results, indent=2, default=str)

