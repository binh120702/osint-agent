import io
import json
from datetime import datetime

import requests
import trafilatura
from PyPDF2 import PdfReader


def get_content_url(url):
    downloaded = trafilatura.fetch_url(url)
    if downloaded is None:
        return None
    content = trafilatura.extract(
        downloaded,
        output_format="json",
        with_metadata=True,
        include_images=True,
    )
    if content is None:
        return None
    return json.loads(content)


def download_pdf(url, save_path=None):
    """
    Downloads a PDF from a URL and optionally saves it.

    Args:
        url (str): URL of the PDF file.
        save_path (str): Optional path to save the PDF locally.

    Returns:
        bytes: The PDF file content as bytes.
    """
    headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36"
    }
    if url[:4] != "http":
        url = "https://" + url
    response = requests.get(url, stream=True, headers=headers)
    response.raise_for_status()

    pdf_bytes = response.content

    if save_path:
        with open(save_path, "wb") as f:
            f.write(pdf_bytes)

    return pdf_bytes


def extract_pdf_text(pdf_bytes):
    """
    Extracts text from a PDF given its bytes.

    Args:
        pdf_bytes (bytes): PDF file content as bytes.

    Returns:
        dict: Extracted metadata and text (title, text, author, categories, filedate).
    """
    text = ""
    pdf_stream = io.BytesIO(pdf_bytes)
    reader = PdfReader(pdf_stream)
    created_date = ""
    try:
        raw_date = reader.metadata.get("/CreationDate")
        if raw_date:
            created_date = datetime.strptime(raw_date[2:16], "%Y%m%d%H%M%S")
    except Exception:
        pass

    for page in reader.pages:
        text += page.extract_text() or ""

    return {
        "title": reader.metadata.title,
        "text": text.strip(),
        "author": reader.metadata.author,
        "categories": reader.metadata.subject,
        "filedate": created_date,
    }
