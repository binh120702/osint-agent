import re
from typing import List, Optional
from urllib.parse import quote, unquote, urlparse

import requests


class WikipediaPage:
    """Fetch and parse Wikipedia page info and search pages by keyword."""

    WIKI_API = "https://en.wikipedia.org/w/api.php"
    WIKI_SUMMARY = "https://en.wikipedia.org/api/rest_v1/page/summary"

    def __init__(self, title: Optional[str] = None, url: Optional[str] = None):
        """
        Initialize WikipediaPage by title or URL.
        """
        if url:
            parsed = urlparse(url)
            path = parsed.path.strip("/")
            if path.startswith("wiki/"):
                path = path[5:]
            self.title = unquote(path)
        elif title:
            self.title = title
        else:
            raise ValueError("Must provide either title or URL")

        self.summary = None
        self.description = None
        self.exists_checked = False
        self.exists_flag = None
        self.is_redirect = None
        self.is_disambiguation = None

        self.session = requests.Session()
        self.session.headers.update(
            {"User-Agent": "WikiFetcherBot/1.0 (https://github.com/yourname; contact@example.com)"}
        )
        self.url = f"https://en.wikipedia.org/wiki/{self.title.replace(' ', '_')}"
        self.categories = []

    def fetch_summary(self):
        encoded_title = quote(self.title)
        params = {
            "action": "query",
            "prop": "categories",
            "titles": self.title,
            "format": "json",
            "clshow": "!hidden",
        }
        url = f"{self.WIKI_SUMMARY}/{encoded_title}"
        resp = self.session.get(url, params=params)
        if resp.status_code != 200:
            raise Exception(f"Wikipedia summary not found ({resp.status_code})")
        data = resp.json()
        self.title = data.get("title", self.title)
        self.summary = data.get("extract")
        self.description = data.get("description")
        self.url = data.get("content_urls", {}).get("desktop", {}).get(
            "page", f"https://en.wikipedia.org/wiki/{encoded_title}"
        )
        return self.summary

    def fetch_categories(self):
        params = {
            "action": "query",
            "prop": "categories",
            "titles": self.title,
            "format": "json",
            "clshow": "!hidden",
        }
        resp = self.session.get(self.WIKI_API, params=params)
        if resp.status_code != 200:
            raise Exception(f"Wikipedia categories not found ({resp.status_code})")
        pages = resp.json().get("query", {}).get("pages", {})
        categories = []
        for page in pages.values():
            for cat in page.get("categories", []):
                categories.append(cat.get("title").replace("Category:", ""))
        self.categories = categories
        return self.categories

    def fetch_all(self):
        self.fetch_summary()
        self.fetch_categories()
        return {
            "title": self.title,
            "description": self.description,
            "url": self.url,
            "summary": self.summary,
            "categories": self.categories,
        }

    def exists(self) -> bool:
        if self.exists_checked:
            return self.exists_flag

        encoded_title = quote(self.title)
        resp = self.session.get(f"{self.WIKI_SUMMARY}/{encoded_title}")

        self.exists_checked = True

        if resp.status_code == 200:
            data = resp.json()
            self.exists_flag = True
            self.is_redirect = data.get("type") == "redirect"
            self.is_disambiguation = data.get("type") == "disambiguation"
            self.title = data.get("title", self.title)
            self.url = data.get("content_urls", {}).get("desktop", {}).get("page", self.url)
        elif resp.status_code == 404:
            self.exists_flag = False
        else:
            raise Exception(f"Wikipedia API error ({resp.status_code}): {resp.text[:200]}")

        return self.exists_flag

    @staticmethod
    def search(keyword: str, limit: int = 10) -> List[dict]:
        params = {
            "action": "query",
            "list": "search",
            "srsearch": keyword,
            "srlimit": limit,
            "format": "json",
        }
        session = requests.Session()
        session.headers.update(
            {"User-Agent": "WikiFetcherBot/1.0 (https://github.com/yourname; contact@example.com)"}
        )
        resp = session.get(WikipediaPage.WIKI_API, params=params)
        if resp.status_code != 200:
            raise Exception(f"Wikipedia search failed ({resp.status_code})")
        data = resp.json()
        results = []
        if "query" not in data.keys() or "search" not in data["query"].keys():
            return results

        TAG_RE = re.compile(r"<[^>]+>")
        for item in data["query"]["search"]:
            results.append(
                {
                    x: item[x] if x != "snippet" else TAG_RE.sub("", item[x])
                    for x in item.keys()
                    if x != "ns"
                }
            )
        return results
