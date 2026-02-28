import base64
import re
from typing import List, Optional

import requests


class GitHubRepo:
    """Fetches and parses GitHub repository info, including metadata, title, overview,
    and supports searching repositories by keyword."""

    GITHUB_API = "https://api.github.com/repos"

    def __init__(
        self,
        owner: Optional[str] = None,
        repo: Optional[str] = None,
        url: Optional[str] = None,
        token: Optional[str] = None,
    ):
        """
        Initialize GitHubRepo by:
        - owner & repo
        - OR URL (e.g., https://github.com/Sajid030/image-caption-generator)
        """
        self.token = token
        self.metadata = {}
        self.title = None
        self.overview = None
        self.readme_text = None

        if url:
            pattern = r"https?://github\.com/([^/]+)/([^/]+)"
            m = re.match(pattern, url)
            if not m:
                raise ValueError(f"Invalid GitHub URL: {url}")
            self.owner, self.repo = m.group(1), m.group(2).replace(".git", "")
        else:
            if not owner or not repo:
                raise ValueError("You must provide either owner/repo or a GitHub URL")
            self.owner = owner
            self.repo = repo

        self.exists_checked = False
        self.exists_flag = None
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "GitHubRepoChecker/1.0",
                "Accept": "application/vnd.github.v3+json",
            }
        )

    def _get(self, endpoint: str):
        url = f"{self.GITHUB_API}/{endpoint}"
        headers = {"Accept": "application/vnd.github+json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            raise Exception(f"GitHub API error ({response.status_code}): {response.text}")
        return response.json()

    def exists(self) -> bool:
        if self.exists_checked:
            return self.exists_flag

        api_url = f"{self.GITHUB_API}/{self.owner}/{self.repo}"
        resp = self.session.head(api_url)
        self.exists_checked = True

        if resp.status_code == 200:
            self.exists_flag = True
        elif resp.status_code in (404, 410):
            self.exists_flag = False
        else:
            resp = self.session.get(api_url)
            self.exists_flag = resp.status_code == 200

        return self.exists_flag

    def fetch_metadata(self):
        data = self._get(f"{self.owner}/{self.repo}")
        self.metadata = {
            "full_name": data.get("full_name"),
            "name": data.get("name"),
            "description": data.get("description"),
            "html_url": data.get("html_url"),
            "language": data.get("language"),
            "stars": data.get("stargazers_count"),
            "forks": data.get("forks_count"),
            "license": data.get("license", {}).get("name") if data.get("license") else None,
            "last_update": data.get("updated_at"),
        }
        return self.metadata

    def fetch_readme(self):
        try:
            data = self._get(f"{self.owner}/{self.repo}/readme")
            self.readme_text = base64.b64decode(data.get("content", "")).decode("utf-8", errors="ignore")
        except Exception:
            self.readme_text = None
        return self.readme_text

    def parse_readme(self):
        if not self.readme_text:
            self.title, self.overview = None, None
            return None, None

        lines = self.readme_text.splitlines()
        title = None
        overview_section = []
        start_collecting = False

        for line in lines:
            if not title and re.match(r"^#\s+", line.strip()):
                title = re.sub(r"^#\s+", "", line.strip())
                continue

            if re.match(r"^#+\s*(overview|abstract|introduction)", line.strip(), re.I):
                start_collecting = True
                continue

            if start_collecting and re.match(r"^#+\s+\w+", line.strip()):
                break

            if start_collecting:
                overview_section.append(line.strip())

        if not overview_section:
            for line in lines:
                if not re.match(r"^#", line) and line.strip():
                    overview_section.append(line.strip())
                elif len(overview_section) > 3:
                    break

        overview_text = " ".join([l for l in overview_section if l])
        self.title = title or self.metadata.get("name")
        self.overview = overview_text.strip() if overview_text else None
        return self.title, self.overview

    def fetch_all(self):
        self.fetch_metadata()
        self.fetch_readme()
        self.parse_readme()
        return {
            "repository": self.metadata,
            "title": self.title,
            "overview": self.overview or "No explicit overview found.",
        }

    def to_dict(self):
        return {
            "repository": self.metadata,
            "title": self.title,
            "overview": self.overview,
        }

    @staticmethod
    def search(
        keyword: str,
        per_page: int = 30,
        max_pages: int = 3,
        language: Optional[str] = None,
        token: Optional[str] = None,
    ) -> List[dict]:
        search_url = "https://api.github.com/search/repositories"
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        repos_list = []
        query = f"{keyword}" + (f" language:{language}" if language else "")

        for page in range(1, max_pages + 1):
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": per_page,
                "page": page,
            }

            response = requests.get(search_url, headers=headers, params=params)
            if response.status_code != 200:
                raise Exception(f"GitHub API search failed ({response.status_code}): {response.text}")

            data = response.json()
            items = data.get("items", [])
            if not items:
                break

            for item in items:
                repo_json = {
                    "full_name": item.get("full_name"),
                    "name": item.get("name"),
                    "description": item.get("description"),
                    "html_url": item.get("html_url"),
                    "language": item.get("language"),
                    "stars": item.get("stargazers_count"),
                    "forks": item.get("forks_count"),
                    "license": item.get("license", {}).get("name") if item.get("license") else None,
                    "last_update": item.get("updated_at"),
                }
                repos_list.append(repo_json)

            if len(items) < per_page:
                break

        return repos_list
