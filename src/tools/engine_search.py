"""
OSINT Web Access - Search Engines & Social Media
Complete implementation with retry logic and rate limiting
"""

from dotenv import load_dotenv
load_dotenv()

from agent.tool_decorator import tool
import requests
import os
from typing import Dict, List, Optional
import time
from datetime import datetime
import json
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin, urlsplit, urlunsplit
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================================================
# 1. WEB SEARCH IMPLEMENTATIONS
# ==================================================

class SearchEngineClient:
    """Base class for search engine clients"""
    
    def __init__(self, max_retries: int = 3, delay: float = 1.0):
        self.max_retries = max_retries
        self.delay = delay
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def retry_with_backoff(self, func, *args, **kwargs):
        """Exponential backoff retry logic"""
        for attempt in range(self.max_retries):
            try:
                return func(*args, **kwargs)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                wait_time = self.delay * (2 ** attempt)
                logger.warning(f"Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)


class GoogleSearchAPI(SearchEngineClient):
    """Google Custom Search API - Best for production"""
    
    def __init__(self, api_key: str, search_engine_id: str):
        super().__init__()
        self.api_key = api_key
        self.search_engine_id = search_engine_id
        self.base_url = "https://www.googleapis.com/customsearch/v1"
    
    def search(self, query: str, num_results: int = 10) -> List[Dict]:
        """
        Search using Google Custom Search API
        Get API key: https://developers.google.com/custom-search/v1/overview
        """
        def _search():
            params = {
                'key': self.api_key,
                'cx': self.search_engine_id,
                'q': query,
                'num': min(num_results, 10)  # Max 10 per request
            }
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            return response.json()
        
        results = self.retry_with_backoff(_search)
        
        return [{
            'title': item.get('title'),
            'url': item.get('link'),
            'snippet': item.get('snippet'),
            'source': 'google'
        } for item in results.get('items', [])]


class DuckDuckGoSearch(SearchEngineClient):
    """DuckDuckGo HTML search with optional Chrome TLS impersonation.

    DuckDuckGo commonly blocks generic HTTP clients based on their TLS
    fingerprint. ``curl_cffi`` can impersonate a real Chrome client and is
    therefore used automatically when the normal request is challenged.
    """

    BLOCK_MARKERS = (
        "captcha",
        "challenge",
        "bot detection",
        "unusual traffic",
        "automated queries",
    )

    def __init__(self):
        super().__init__()
        try:
            self.max_retries = max(1, min(int(os.getenv("DDG_MAX_RETRIES", "2")), 3))
        except ValueError:
            self.max_retries = 2
        try:
            self.timeout = max(3, min(float(os.getenv("DDG_TIMEOUT", "12")), 60))
        except ValueError:
            self.timeout = 12.0
        self.backend = os.getenv("DDG_SEARCH_BACKEND", "auto").strip().lower()
        if self.backend not in {"auto", "requests", "curl"}:
            logger.warning("Invalid DDG_SEARCH_BACKEND=%s; using auto", self.backend)
            self.backend = "auto"
        self.region = os.getenv("DDG_REGION", "").strip()
        self.safe_search = os.getenv("DDG_SAFE_SEARCH", "MODERATE").strip().upper()
        self.impersonate = os.getenv("DDG_CURL_IMPERSONATE", "chrome131").strip()
        self.proxy = os.getenv("DDG_PROXY", "").strip() or None

    @classmethod
    def _is_blocked(cls, status_code: int, body: str) -> bool:
        if status_code in (202, 403):
            return True
        if not body.strip():
            return True
        body_lower = body.lower()
        return any(marker in body_lower for marker in cls.BLOCK_MARKERS) and not ".result" in body_lower

    def _curl_search(self, query: str) -> str:
        try:
            from curl_cffi import requests as curl_requests
        except ImportError as exc:
            raise RuntimeError(
                "DuckDuckGo requires curl-cffi for Chrome TLS impersonation. "
                "Install project dependencies or set DDG_SEARCH_BACKEND=requests."
            ) from exc

        response = curl_requests.post(
            "https://html.duckduckgo.com/html",
            data={
                "q": query,
                "b": "",
                "kl": self.region,
                "kp": {"OFF": "-2", "MODERATE": "", "STRICT": "1"}.get(self.safe_search, ""),
            },
            impersonate=self.impersonate,
            timeout=self.timeout,
            proxy=self.proxy,
        )
        response.raise_for_status()
        if self._is_blocked(response.status_code, response.text):
            raise RuntimeError(f"DuckDuckGo returned a blocked response (HTTP {response.status_code})")
        return response.text
    
    def search(self, query: str, num_results: int = 20) -> List[Dict]:
        """
        DuckDuckGo HTML scraping (no official API)
        Note: For production, consider using their unofficial API or official methods
        """
        def _requests_search():
            response = self.session.post(
                "https://html.duckduckgo.com/html",
                data={
                    "q": query,
                    "b": "",
                    "kl": self.region,
                    "kp": {"OFF": "-2", "MODERATE": "", "STRICT": "1"}.get(self.safe_search, ""),
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            if self._is_blocked(response.status_code, response.text):
                raise RuntimeError(f"DuckDuckGo returned a blocked response (HTTP {response.status_code})")
            return response.text

        if self.backend == "curl":
            html = self.retry_with_backoff(self._curl_search, query)
        else:
            try:
                html = self.retry_with_backoff(_requests_search)
            except Exception:
                if self.backend != "auto":
                    raise
                logger.info("DuckDuckGo normal HTTP request was blocked; retrying with Chrome TLS impersonation")
                html = self.retry_with_backoff(self._curl_search, query)

        soup = BeautifulSoup(html, 'html.parser')
        
        results = []
        for result in soup.select('.result')[:num_results]:
            title_elem = result.select_one('.result__title')
            snippet_elem = result.select_one('.result__snippet')
            link_elem = result.select_one('.result__title a') or result.select_one('.result__url')

            if title_elem and link_elem:
                results.append({
                    'title': title_elem.get_text(strip=True),
                    'url': link_elem.get('href', ''),
                    'snippet': snippet_elem.get_text(strip=True) if snippet_elem else '',
                    'source': 'duckduckgo'
                })
        
        return results


class SearxngSearch(SearchEngineClient):
    """SearXNG Search Engine - Configurable instance or fallback list"""
    
    def __init__(self, base_url: Optional[str] = None):
        super().__init__()
        self.configured_url = base_url or os.getenv("SEARXNG_URL", "").strip()
        self.fallback_instances = [
            "https://searx.be",
            "https://searxng.site",
            "https://searx.work",
            "https://priv.au",
        ]

    def search(self, query: str, num_results: int = 20) -> List[Dict]:
        if self.configured_url:
            urls = [self.configured_url]
        else:
            urls = self.fallback_instances

        for url in urls:
            search_url = url if url.endswith("/search") else urljoin(url, "search")
            try:
                def _search():
                    params = {
                        'q': query,
                        'format': 'json',
                        'pageno': '1'
                    }
                    response = self.session.get(search_url, params=params, timeout=8)
                    response.raise_for_status()
                    return response.json()
                
                results = self.retry_with_backoff(_search)
                items = results.get('results', [])
                if items:
                    return [{
                        'title': item.get('title'),
                        'url': item.get('url'),
                        'snippet': item.get('content') or item.get('snippet') or '',
                        'source': 'searxng'
                    } for item in items[:num_results]]
            except Exception as e:
                logger.warning(f"SearXNG instance {url} failed: {e}. Trying next...")
                continue
        
        return []



class BingSearchAPI(SearchEngineClient):
    """Bing Search API - Good alternative to Google"""
    
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
        self.base_url = "https://api.bing.microsoft.com/v7.0/search"
        self.session.headers.update({'Ocp-Apim-Subscription-Key': api_key})
    
    def search(self, query: str, num_results: int = 10) -> List[Dict]:
        """
        Bing Web Search API
        Get API key: https://www.microsoft.com/en-us/bing/apis/bing-web-search-api
        """
        def _search():
            params = {'q': query, 'count': num_results}
            response = self.session.get(self.base_url, params=params)
            response.raise_for_status()
            return response.json()
        
        results = self.retry_with_backoff(_search)
        
        return [{
            'title': item.get('name'),
            'url': item.get('url'),
            'snippet': item.get('snippet'),
            'source': 'bing'
        } for item in results.get('webPages', {}).get('value', [])]


# ==================================================
# 2. SOCIAL MEDIA IMPLEMENTATIONS
# ==================================================

class TwitterScraper(SearchEngineClient):
    """
    Twitter/X scraping
    Options:
    1. Official API (requires approval)
    2. Unofficial libraries: tweepy, snscrape
    3. Third-party APIs: Apify, ScraperAPI
    """
    
    def __init__(self, bearer_token: str):
        super().__init__()
        self.bearer_token = bearer_token
        self.base_url = "https://api.twitter.com/2"
        self.session.headers.update({'Authorization': f'Bearer {bearer_token}'})
    
    def search_tweets(self, query: str, max_results: int = 10) -> List[Dict]:
        """
        Search tweets using Twitter API v2
        Get bearer token: https://developer.twitter.com/
        """
        def _search():
            params = {
                'query': query,
                'max_results': min(max_results, 100),
                'tweet.fields': 'created_at,author_id,public_metrics'
            }
            response = self.session.get(f"{self.base_url}/tweets/search/recent", params=params)
            response.raise_for_status()
            return response.json()
        
        results = self.retry_with_backoff(_search)
        
        return [{
            'text': tweet.get('text'),
            'created_at': tweet.get('created_at'),
            'author_id': tweet.get('author_id'),
            'metrics': tweet.get('public_metrics'),
            'source': 'twitter'
        } for tweet in results.get('data', [])]
    
    def get_user_info(self, username: str) -> Dict:
        """Get user profile information"""
        def _get():
            url = f"{self.base_url}/users/by/username/{username}"
            params = {'user.fields': 'description,created_at,public_metrics,verified'}
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        
        return self.retry_with_backoff(_get)


class RedditScraper(SearchEngineClient):
    """Reddit API - Very accessible, good documentation"""
    
    def __init__(self, client_id: str, client_secret: str, user_agent: str):
        super().__init__()
        self.client_id = client_id
        self.client_secret = client_secret
        self.user_agent = user_agent
        self.base_url = "https://oauth.reddit.com"
        self._authenticate()
    
    def _authenticate(self):
        """Get OAuth token"""
        auth = requests.auth.HTTPBasicAuth(self.client_id, self.client_secret)
        data = {'grant_type': 'client_credentials'}
        headers = {'User-Agent': self.user_agent}
        
        response = requests.post(
            'https://www.reddit.com/api/v1/access_token',
            auth=auth,
            data=data,
            headers=headers
        )
        response.raise_for_status()
        token = response.json()['access_token']
        
        self.session.headers.update({
            'Authorization': f'Bearer {token}',
            'User-Agent': self.user_agent
        })
    
    def search(self, query: str, subreddit: Optional[str] = None, limit: int = 25) -> List[Dict]:
        """Search Reddit posts"""
        def _search():
            if subreddit:
                url = f"{self.base_url}/r/{subreddit}/search"
            else:
                url = f"{self.base_url}/search"
            
            params = {
                'q': query,
                'limit': limit,
                'sort': 'relevance'
            }
            if subreddit:
                params['restrict_sr'] = 'true'
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            return response.json()
        
        results = self.retry_with_backoff(_search)
        
        return [{
            'title': post['data'].get('title'),
            'text': post['data'].get('selftext'),
            'author': post['data'].get('author'),
            'subreddit': post['data'].get('subreddit'),
            'score': post['data'].get('score'),
            'url': post['data'].get('url'),
            'created_utc': post['data'].get('created_utc'),
            'source': 'reddit'
        } for post in results.get('data', {}).get('children', [])]
    
    def get_user_info(self, username: str) -> Dict:
        """Get Reddit user information"""
        def _get():
            url = f"{self.base_url}/user/{username}/about"
            response = self.session.get(url)
            response.raise_for_status()
            return response.json()
        
        return self.retry_with_backoff(_get)


class LinkedInScraper(SearchEngineClient):
    """
    LinkedIn scraping (most restricted)
    Options:
    1. Official API (very limited access)
    2. Third-party: Proxycurl, ScraperAPI, Bright Data
    3. Selenium/Playwright (requires login, against ToS)
    """
    
    def __init__(self, api_key: str):
        super().__init__()
        self.api_key = api_key
        # Using Proxycurl as example
        self.base_url = "https://nubela.co/proxycurl/api/v2"
        self.session.headers.update({'Authorization': f'Bearer {api_key}'})
    
    def get_profile(self, linkedin_url: str) -> Dict:
        """
        Get LinkedIn profile via Proxycurl
        https://nubela.co/proxycurl/
        """
        def _get():
            params = {'url': linkedin_url}
            response = self.session.get(
                f"{self.base_url}/linkedin",
                params=params
            )
            response.raise_for_status()
            return response.json()
        
        return self.retry_with_backoff(_get)


class GitHubScraper(SearchEngineClient):
    """GitHub API - Excellent documentation, generous rate limits"""
    
    def __init__(self, token: Optional[str] = None):
        super().__init__()
        self.base_url = "https://api.github.com"
        if token:
            self.session.headers.update({'Authorization': f'token {token}'})
    
    def search_users(self, query: str, max_results: int = 30) -> List[Dict]:
        """Search GitHub users"""
        def _search():
            params = {'q': query, 'per_page': min(max_results, 100)}
            response = self.session.get(f"{self.base_url}/search/users", params=params)
            response.raise_for_status()
            return response.json()
        
        results = self.retry_with_backoff(_search)
        
        return [{
            'username': user.get('login'),
            'profile_url': user.get('html_url'),
            'avatar_url': user.get('avatar_url'),
            'type': user.get('type'),
            'source': 'github'
        } for user in results.get('items', [])]
    
    def get_user_info(self, username: str) -> Dict:
        """Get detailed user information"""
        def _get():
            response = self.session.get(f"{self.base_url}/users/{username}")
            response.raise_for_status()
            return response.json()
        
        return self.retry_with_backoff(_get)


# ==================================================
# 3. UNIFIED OSINT AGGREGATOR
# ==================================================

class OSINTAggregator:
    """Combines multiple sources for comprehensive OSINT"""
    
    def __init__(self):
        logger.info("Initializing OSINTAggregator")
        self.results = []
    
    def add_search_engine(self, name: str, client: SearchEngineClient):
        """Register a search engine"""
        setattr(self, f"search_{name}", client)
    
    def add_social_media(self, name: str, client: SearchEngineClient):
        """Register a social media scraper"""
        setattr(self, f"social_{name}", client)
    
    def aggregate_search(self, query: str, sources: List[str]) -> Dict:
        """
        Search across multiple sources
        sources: ['google', 'bing', 'duckduckgo']
        """
        results = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'sources': {}
        }
        
        for source in sources:
            try:
                client = getattr(self, f"search_{source}", None)
                if client:
                    logger.info(f"Searching {source}...")
                    results['sources'][source] = client.search(query)
                    time.sleep(1)  # Rate limiting
            except Exception as e:
                logger.error(f"Error searching {source}: {e}")
                results['sources'][source] = {'error': str(e)}
        
        return results

    def aggregate_search_merged(self, query: str, sources: List[str], num_results: int = 20) -> Dict:
        """Search sources independently and return source buckets plus deduped results."""
        results = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'sources': {},
            'merged_results': [],
            'errors': {},
        }

        def run(source):
            client = getattr(self, f"search_{source}", None)
            if not client:
                raise RuntimeError(f"Search source is not configured: {source}")
            return client.search(query, num_results=num_results)

        with ThreadPoolExecutor(max_workers=max(1, len(sources))) as executor:
            futures = {executor.submit(run, source): source for source in sources}
            for future in as_completed(futures):
                source = futures[future]
                try:
                    results['sources'][source] = future.result()
                except Exception as exc:
                    logger.error("Error searching %s: %s", source, exc)
                    results['sources'][source] = []
                    results['errors'][source] = str(exc)

        seen = {}
        for source in sources:
            for item in results['sources'].get(source, []):
                url = item.get('url') or ''
                parts = urlsplit(url)
                key = urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query, '')) if parts.scheme else url
                if not key:
                    continue
                if key not in seen:
                    seen[key] = dict(item)
                    seen[key]['sources'] = [source]
                    results['merged_results'].append(seen[key])
                elif source not in seen[key]['sources']:
                    seen[key]['sources'].append(source)
        return results
    
    def aggregate_social(self, query: str, sources: List[str]) -> Dict:
        """
        Search social media across multiple platforms
        sources: ['twitter', 'reddit', 'github']
        """
        results = {
            'query': query,
            'timestamp': datetime.now().isoformat(),
            'platforms': {}
        }
        
        for source in sources:
            try:
                client = getattr(self, f"social_{source}", None)
                if client:
                    logger.info(f"Searching {source}...")
                    if source == 'twitter':
                        results['platforms'][source] = client.search_tweets(query)
                    elif source == 'reddit':
                        results['platforms'][source] = client.search(query)
                    elif source == 'github':
                        results['platforms'][source] = client.search_users(query)
                    time.sleep(1)
            except Exception as e:
                logger.error(f"Error searching {source}: {e}")
                results['platforms'][source] = {'error': str(e)}
        
        return results


# ==================================================
# 4. USAGE EXAMPLES
# ==================================================

def example_usage():
    """Complete usage example"""
    
    # Initialize search engines
    aggregator = OSINTAggregator()
    
    # Add search engines (use your actual API keys)
    # aggregator.add_search_engine('google', GoogleSearchAPI('YOUR_API_KEY', 'YOUR_CX'))
    # aggregator.add_search_engine('bing', BingSearchAPI('YOUR_API_KEY'))
    aggregator.add_search_engine('duckduckgo', DuckDuckGoSearch())
    
    # Add social media scrapers
    # aggregator.add_social_media('twitter', TwitterScraper('YOUR_BEARER_TOKEN'))
    # aggregator.add_social_media('reddit', RedditScraper('CLIENT_ID', 'SECRET', 'USER_AGENT'))
    # aggregator.add_social_media('github', GitHubScraper('YOUR_TOKEN'))
    
    # Search across sources
    query = "cybersecurity breach 2024"
    
    # Web search
    web_results = aggregator.aggregate_search(
        query=query,
        sources=['duckduckgo']  # Add 'google', 'bing' when you have keys
    )
    
    print(json.dumps(web_results, indent=2))
    
    # Social media search
    # social_results = aggregator.aggregate_social(
    #     query=query,
    #     sources=['reddit', 'github']
    # )
    # print(json.dumps(social_results, indent=2))


AGGREGATOR = OSINTAggregator()
AGGREGATOR.add_search_engine('searxng', SearxngSearch())
AGGREGATOR.add_search_engine('duckduckgo', DuckDuckGoSearch())
DDG_ENABLED = os.getenv("DDG_ENABLED", "0").strip().lower() in {"1", "true", "yes", "on"}

@tool
def engine_search_tool(query: str) -> str:
    """
    Search the web using the engine search tool, input the query to search the web for.
    You can use the engine_search tool to search the web for information about the object of investigation.
    Args:
        query: The query to search the web for.
        
    Returns:
        Something with the information of the search results.
    """
    logger.info(f"Searching the web using the engine search tool: {query}")
    sources = ['searxng', 'duckduckgo'] if DDG_ENABLED else ['searxng']
    results = AGGREGATOR.aggregate_search_merged(query, sources)
        
    logger.info(f"Results: {json.dumps(results, indent=2, default=str)}")
    return json.dumps(results, indent=2, default=str)


@tool
def duckduckgo_search(query: str) -> str:
    """Search DuckDuckGo directly using the configured anti-bot-capable backend."""
    if not DDG_ENABLED:
        return json.dumps({
            "query": query,
            "sources": {},
            "merged_results": [],
            "errors": {"duckduckgo": "DuckDuckGo search is disabled (set DDG_ENABLED=1 to enable it)."},
        }, indent=2)
    logger.info("Searching DuckDuckGo directly: %s", query)
    results = AGGREGATOR.aggregate_search_merged(query, ['duckduckgo'])
    return json.dumps(results, indent=2, default=str)


if __name__ == "__main__":
    example_usage()
