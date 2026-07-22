import json

from agent.tool_decorator import tool

from crawlers import download_pdf, extract_pdf_text, get_content_url


@tool
def get_url_content(url: str) -> str:
    """Fetch and extract main article content from a URL using trafilatura.

    Args:
        url: The URL of the web page to extract.

    Returns:
        JSON string with structured content and metadata.
    """
    data = get_content_url(url) 
    if data is None:
        return "No content found for the given URL."
    return json.dumps(data, indent=2, default=str)


@tool
def get_pdf_content(url: str) -> str:
    """Download a PDF from a URL and extract its text and basic metadata.

    Args:
        url: Direct URL of the PDF file or a page that resolves to a PDF.

    Returns:
        JSON string with title, text, author, categories/subject, and filedate.
    """
    pdf_bytes = download_pdf(url)
    extracted = extract_pdf_text(pdf_bytes)
    return json.dumps(extracted, indent=2, default=str)

