import json
from typing import Optional

from langchain.tools import tool

from crawlers import GitHubRepo


def _parse_owner_repo(url_or_owner_repo: str) -> tuple[str, str]:
    """Parse either 'owner/repo' or a full GitHub URL into (owner, repo)."""
    text = url_or_owner_repo.strip()
    if text.startswith("http"):
        repo = GitHubRepo(url=text)
        return repo.owner, repo.repo

    if "/" not in text:
        raise ValueError("Expected 'owner/repo' or a full GitHub URL.")

    owner, repo = text.split("/", 1)
    return owner.strip(), repo.strip()


@tool
def github_repo_summary(url_or_owner_repo: str, token: Optional[str] = None) -> str:
    """Get metadata and overview for a GitHub repository.

    Args:
        url_or_owner_repo: 'owner/repo' or full GitHub URL.
        token: Optional GitHub token to avoid rate limits.

    Returns:
        JSON string with repository metadata, title, and overview text.
    """
    owner, repo_name = _parse_owner_repo(url_or_owner_repo)
    repo = GitHubRepo(owner=owner, repo=repo_name, token=token)
    data = repo.fetch_all()
    return json.dumps(data, indent=2, default=str)


@tool
def github_search_repos(
    keyword: str,
    language: Optional[str] = None,
    per_page: int = 10,
    max_pages: int = 1,
    token: Optional[str] = None,
) -> str:
    """Search GitHub repositories by keyword and optional language.

    Args:
        keyword: Search query.
        language: Optional language filter (e.g. 'Python').
        per_page: Repos per page (default 10).
        max_pages: Number of pages to fetch (default 1).
        token: Optional GitHub token to avoid rate limits.

    Returns:
        JSON string list of repository summaries (name, stars, url, etc.).
    """
    repos = GitHubRepo.search(
        keyword=keyword,
        per_page=per_page,
        max_pages=max_pages,
        language=language,
        token=token,
    )
    return json.dumps(repos, indent=2, default=str)

