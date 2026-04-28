"""
Website Scraping & Data Extraction for OSINT
Complete implementation for investigating personal websites
"""

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse, parse_qs
from langchain.tools import tool

import requests
from bs4 import BeautifulSoup

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================================================
# 1. BASIC WEBSITE FETCHER
# ==================================================

class WebsiteFetcher:
    """Fetch website content with proper headers and error handling"""
    
    def __init__(self, timeout: int = 10, max_retries: int = 3):
        self.timeout = timeout
        self.max_retries = max_retries
        self.session = requests.Session()
        
        # Mimic real browser to avoid blocking
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def fetch(self, url: str) -> Dict:
        """
        Fetch a webpage with retry logic
        Returns: Dict with html, status_code, headers, etc.
        """
        for attempt in range(self.max_retries):
            try:
                logger.info(f"Fetching {url} (attempt {attempt + 1}/{self.max_retries})")
                
                response = self.session.get(
                    url,
                    timeout=self.timeout,
                    allow_redirects=True,
                    verify=True  # Verify SSL certificates
                )
                
                return {
                    'success': True,
                    'url': response.url,  # Final URL after redirects
                    'status_code': response.status_code,
                    'headers': dict(response.headers),
                    'html': response.text,
                    'content': response.content,  # Raw bytes
                    'encoding': response.encoding,
                    'history': [r.url for r in response.history],  # Redirect chain
                    'timestamp': datetime.now().isoformat()
                }
                
            except requests.exceptions.Timeout:
                logger.warning(f"Timeout on attempt {attempt + 1}")
                if attempt == self.max_retries - 1:
                    return {'success': False, 'error': 'Timeout'}
                time.sleep(2 ** attempt)
                
            except requests.exceptions.SSLError as e:
                logger.warning(f"SSL Error: {e}")
                # Try without SSL verification (risky, note in report)
                try:
                    response = self.session.get(url, timeout=self.timeout, verify=False)
                    result = {
                        'success': True,
                        'url': response.url,
                        'status_code': response.status_code,
                        'headers': dict(response.headers),
                        'html': response.text,
                        'warning': 'SSL verification failed - potential security risk',
                        'timestamp': datetime.now().isoformat()
                    }
                    return result
                except Exception as e2:
                    return {'success': False, 'error': f'SSL Error: {str(e2)}'}
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"Request error: {e}")
                if attempt == self.max_retries - 1:
                    return {'success': False, 'error': str(e)}
                time.sleep(2 ** attempt)
        
        return {'success': False, 'error': 'Max retries exceeded'}


# ==================================================
# 2. HTML PARSER & DATA EXTRACTOR
# ==================================================

@dataclass
class ExtractedData:
    """Structure for extracted website data"""
    url: str
    title: Optional[str] = None
    meta_description: Optional[str] = None
    meta_keywords: Optional[str] = None
    external_links: List[str] = None
    internal_links: List[str] = None
    images: List[Dict] = None
    text_content: str = None
    author: Optional[str] = None
    timestamp: str = None
    
    def __post_init__(self):
        if self.external_links is None:
            self.external_links = []
        if self.internal_links is None:
            self.internal_links = []
        if self.images is None:
            self.images = []
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class HTMLParser:
    """Parse HTML and extract relevant information"""

    def __init__(self, base_url: str):
        self.base_url = base_url
        self.domain = urlparse(base_url).netloc
    
    def parse(self, html: str) -> ExtractedData:
        """Parse HTML and extract all useful information"""
        soup = BeautifulSoup(html, 'html.parser')
        
        data = ExtractedData(url=self.base_url)
        
        # Basic metadata
        data.title = self._extract_title(soup)
        data.meta_description = self._extract_meta(soup, 'description')
        data.meta_keywords = self._extract_meta(soup, 'keywords')
        data.author = self._extract_meta(soup, 'author')
        
        # Links
        data.internal_links, data.external_links = self._extract_links(soup)
        
        # Media
        data.images = self._extract_images(soup)
        
        # Text content
        data.text_content = self._extract_text(soup)
        
        return data
    
    def _extract_title(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract page title"""
        title = soup.find('title')
        return title.string.strip() if title else None
    
    def _extract_meta(self, soup: BeautifulSoup, name: str) -> Optional[str]:
        """Extract meta tag content"""
        meta = soup.find('meta', attrs={'name': name})
        if not meta:
            meta = soup.find('meta', attrs={'property': f'og:{name}'})
        return meta.get('content', '').strip() if meta else None
    
    def _extract_links(self, soup: BeautifulSoup) -> tuple[List[str], List[str]]:
        """Separate internal and external links"""
        internal = []
        external = []
        
        for link in soup.find_all('a', href=True):
            href = link['href']
            absolute_url = urljoin(self.base_url, href)
            
            if urlparse(absolute_url).netloc == self.domain:
                internal.append(absolute_url)
            else:
                if absolute_url.startswith('http'):
                    external.append(absolute_url)
        
        return list(set(internal)), list(set(external))
    
    def _extract_images(self, soup: BeautifulSoup) -> List[Dict]:
        """Extract all images with metadata"""
        images = []
        
        for img in soup.find_all('img'):
            images.append({
                'src': urljoin(self.base_url, img.get('src', '')),
                'alt': img.get('alt', ''),
                'title': img.get('title', ''),
                'width': img.get('width', ''),
                'height': img.get('height', '')
            })
        
        return images
    
    def _extract_text(self, soup: BeautifulSoup) -> str:
        """Extract clean text content"""
        # Remove script and style elements
        for script in soup(['script', 'style', 'nav', 'footer', 'header']):
            script.decompose()
        
        text = soup.get_text(separator=' ', strip=True)
        # Clean up whitespace
        text = re.sub(r'\s+', ' ', text)
        
        return text


# ==================================================
# 3. WEBSITE CRAWLER (Multi-page)
# ==================================================

class WebsiteCrawler:
    """Crawl multiple pages of a website"""
    
    def __init__(self, max_pages: int = 50, delay: float = 1.0):
        self.max_pages = max_pages
        self.delay = delay
        self.fetcher = WebsiteFetcher()
        self.visited = set()
        self.to_visit = []
    
    def crawl(self, start_url: str, same_domain_only: bool = True) -> List[ExtractedData]:
        """
        Crawl a website starting from start_url
        Returns: List of ExtractedData for each page
        """
        self.to_visit = [start_url]
        self.visited = set()
        results = []
        
        domain = urlparse(start_url).netloc
        
        while self.to_visit and len(self.visited) < self.max_pages:
            url = self.to_visit.pop(0)
            
            if url in self.visited:
                continue
            
            logger.info(f"Crawling: {url} ({len(self.visited)}/{self.max_pages})")
            
            # Fetch page
            response = self.fetcher.fetch(url)
            if not response.get('success'):
                logger.error(f"Failed to fetch {url}: {response.get('error')}")
                continue
            
            self.visited.add(url)
            
            # Parse page
            parser = HTMLParser(url)
            data = parser.parse(response['html'])
            results.append(data)
            
            # Add internal links to queue
            if same_domain_only:
                for link in data.internal_links:
                    if link not in self.visited and link not in self.to_visit:
                        self.to_visit.append(link)
            
            # Rate limiting
            time.sleep(self.delay)
        
        logger.info(f"Crawl complete. Visited {len(self.visited)} pages.")
        return results


# ==================================================
# 4. COMPLETE OSINT WEBSITE INVESTIGATOR
# ==================================================

class WebsiteInvestigator:
    """Complete website investigation tool"""
    
    def __init__(self):
        self.fetcher = WebsiteFetcher()
        self.crawler = WebsiteCrawler()
    
    def investigate(self, urls, deep_crawl: bool = False) -> Dict:
        """
        Complete investigation of website(s)
        
        Args:
            urls: Single URL string or list of URLs to investigate
            deep_crawl: If True, crawl each URL's domain for additional pages
        
        Returns:
            Dict with all extracted information from all pages
        """
        # Convert single URL to list
        if isinstance(urls, str):
            urls = [urls]
        
        logger.info(f"Starting investigation of {len(urls)} URL(s)")
        
        investigation = {
            'target_urls': urls,
            'timestamp': datetime.now().isoformat(),
            'pages': [],
        }
        
        for url in urls:
            logger.info(f"Investigating: {url}")
            
            # Fetch the page
            response = self.fetcher.fetch(url)
            if not response.get('success'):
                logger.error(f"Failed to fetch {url}: {response.get('error')}")
                investigation['pages'].append({
                    'url': url,
                    'error': response.get('error'),
                    'status_code': response.get('status_code', 'N/A')
                })
                continue
            
            # Parse the page
            parser = HTMLParser(response['url'])  # Use final URL after redirects
            data = parser.parse(response['html'])
            
            # Add fetch metadata
            page_result = asdict(data)
            page_result['fetch_metadata'] = {
                'status_code': response.get('status_code'),
                'headers': response.get('headers', {}),
                'redirects': response.get('history', [])
            }
            
            investigation['pages'].append(page_result)
            
            # If deep crawl is enabled, crawl the domain
            if deep_crawl:
                domain = urlparse(url).netloc
                logger.info(f"Deep crawling domain: {domain}")
                pages_data = self.crawler.crawl(url, same_domain_only=True)
                
                # Add crawled pages (avoid duplicating the initial page)
                for page_data in pages_data:
                    if page_data.url != response['url']:
                        investigation['pages'].append(asdict(page_data))
        
        logger.info(f"Investigation complete. Processed {len(investigation['pages'])} pages")
        return investigation
    
    def investigate_multiple_pages(self, pages: List[str]) -> Dict:
        """Convenience method: Investigate multiple pages (alias for investigate)"""
        return self.investigate(pages)
    
    def _generate_summary(self, pages: List[Dict]) -> Dict:
        """Generate summary from all crawled pages"""
        all_external_links = set()
        
        for page in pages:
            all_external_links.update(page.get('external_links', []))
        
        return {
            'total_pages_crawled': len(pages),
            'unique_external_links': len(all_external_links),
            'top_external_domains': self._get_top_domains(all_external_links)
        }
    
    def _get_top_domains(self, links: Set[str], top_n: int = 10) -> List[tuple]:
        """Get most frequently linked external domains"""
        from collections import Counter
        domains = [urlparse(link).netloc for link in links]
        return Counter(domains).most_common(top_n)
    
    def save_offline_copy(self, url: str, output_dir: str = "offline_copy"):
        """Download entire website for offline analysis"""
        Path(output_dir).mkdir(exist_ok=True)
        
        # Crawl site
        pages_data = self.crawler.crawl(url)
        
        for i, page in enumerate(pages_data):
            # Save HTML
            filename = f"page_{i}_{hashlib.md5(page.url.encode()).hexdigest()[:8]}.html"
            filepath = Path(output_dir) / filename
            
            # Re-fetch to get original HTML
            response = self.fetcher.fetch(page.url)
            if response.get('success'):
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(response['html'])
                
                logger.info(f"Saved: {filepath}")
        
        # Save investigation report
        investigation = self.investigate(url, deep_crawl=False)
        report_path = Path(output_dir) / "investigation_report.json"
        with open(report_path, 'w', encoding='utf-8') as f:
            json.dump(investigation, f, indent=2, default=str)
        
        logger.info(f"Investigation complete. Files saved to {output_dir}/")


# ==================================================
# 5. USAGE EXAMPLES
# ==================================================

def example_single_page(url_to_investigate):
    """Example: Investigate single page"""
    investigator = WebsiteInvestigator()
    
    # Investigate a single page
    result = investigator.investigate(
        urls=url_to_investigate,
        deep_crawl=False
    )
    
    print(json.dumps(result, indent=2, default=str))


def example_deep_crawl():
    """Example: Deep crawl entire website"""
    investigator = WebsiteInvestigator()
    
    # Deep crawl up to 50 pages
    result = investigator.investigate(
        urls="https://nl.pinterest.com/gouldieloxx/",
        deep_crawl=True
    )
    
    # Print results
    print("=" * 50)
    print("INVESTIGATION SUMMARY")
    print("=" * 50)
    print(f"Pages crawled: {len(result['pages'])}")
    
    # Display summary of external links
    summary = investigator._generate_summary(result['pages'])
    print(f"Unique external links: {summary['unique_external_links']}")
    print(f"Top external domains: {summary['top_external_domains']}")


def example_multiple_urls():
    """Example: Investigate multiple URLs from different sources"""
    investigator = WebsiteInvestigator()
    
    # Investigate multiple URLs from different domains
    urls = [
        "https://example.com/about",
        "https://another-site.com/contact",
        "https://third-site.com/team"
    ]
    
    result = investigator.investigate(
        urls=urls,
        deep_crawl=False
    )
    
    print(json.dumps(result, indent=2, default=str))


def example_offline_copy(url_to_investigate):
    """Example: Save offline copy"""
    investigator = WebsiteInvestigator()
    
    # Download entire site
    investigator.save_offline_copy(
        url=url_to_investigate if isinstance(url_to_investigate, str) else url_to_investigate[0],
        output_dir="evidence/"
    )


@tool
def deep_search(pages: list[str]) -> str:
    """
        Deep search one or more web pages (URLs) and extract text/links/images.

        This tool is intentionally **bounded** for safety and predictability:
        - It will investigate the URLs you provide.
        - It will also *optionally* discover extra URLs from each site's `robots.txt`
          (both Allow and Disallow paths) and expand simple pagination patterns
          like `/page/1`..`/page/5`, but only up to small fixed limits.

    Args:
        pages: The list of pages to investigate.
    Returns:
        Something with the information of the website.
    """
    logger.info(f"Deep searching multiple pages: {pages}")

    def _origin(url: str) -> str:
        p = urlparse(url)
        if not p.scheme or not p.netloc:
            return ""
        return f"{p.scheme}://{p.netloc}"

    def _robots_url(url: str) -> str:
        o = _origin(url)
        return f"{o}/robots.txt" if o else ""

    def _parse_robots_txt(text: str, base: str) -> List[str]:
        """
        Very lightweight robots.txt parser:
        - Collects Allow/Disallow path values
        - Ignores user-agent grouping (we just want candidate URLs)
        """
        urls: List[str] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" not in line:
                continue
            k, v = line.split(":", 1)
            key = k.strip().lower()
            value = v.strip()
            if key not in {"allow", "disallow", "sitemap"}:
                continue
            if key == "sitemap":
                if value.startswith("http://") or value.startswith("https://"):
                    urls.append(value)
                continue
            # Allow/Disallow paths are usually relative.
            if value and value != "/":
                urls.append(urljoin(base, value))
        return urls

    def _expand_pagination(urls: List[str], max_new: int) -> List[str]:
        """
        Expand simple pagination patterns like `/page/1`..`/page/5`.
        Only expands within the same (scheme, netloc, path prefix) bucket.
        """
        expanded: Set[str] = set()
        buckets: Dict[str, Set[int]] = {}
        pattern = re.compile(r"^(.*?)(\d+)(/?)(\?.*)?$")

        for u in urls:
            m = pattern.match(u)
            if not m:
                continue
            prefix, num_str, slash, qs = m.group(1), m.group(2), m.group(3), m.group(4) or ""
            # Heuristic: only treat as pagination if prefix ends with /page/ or page=
            if not (prefix.endswith("/page/") or "page=" in (prefix + qs)):
                continue
            try:
                n = int(num_str)
            except ValueError:
                continue
            key = f"{prefix}|{slash}|{qs}"
            buckets.setdefault(key, set()).add(n)

        for key, nums in buckets.items():
            if len(expanded) >= max_new:
                break
            if len(nums) < 2:
                continue
            min_n, max_n = min(nums), max(nums)
            # Bound the range so we don't explode.
            if max_n - min_n > 25:
                continue
            prefix, slash, qs = key.split("|", 2)
            for n in range(min_n, max_n + 1):
                if len(expanded) >= max_new:
                    break
                expanded.add(f"{prefix}{n}{slash}{qs}")

        return list(expanded)

    # Bounded discovery limits
    MAX_TOTAL_URLS = 30
    MAX_ROBOTS_URLS_PER_ORIGIN = 15
    MAX_PAGINATION_EXPANSION = 15

    provided = [p for p in pages if isinstance(p, str) and p.strip()]
    candidate_urls: List[str] = []
    seen: Set[str] = set()

    def _add(u: str):
        if not u or u in seen:
            return
        if len(seen) >= MAX_TOTAL_URLS:
            return
        seen.add(u)
        candidate_urls.append(u)

    for u in provided:
        _add(u.strip())

    # robots.txt discovery (best effort)
    origins = list({o for o in (_origin(u) for u in provided) if o})
    fetcher = WebsiteFetcher(timeout=10, max_retries=2)
    for o in origins:
        if len(candidate_urls) >= MAX_TOTAL_URLS:
            break
        rurl = f"{o}/robots.txt"
        try:
            r = fetcher.fetch(rurl)
            if not r.get("success") or not isinstance(r.get("html"), str):
                continue
            robots_candidates = _parse_robots_txt(r["html"], o)
            for rc in robots_candidates[:MAX_ROBOTS_URLS_PER_ORIGIN]:
                _add(rc)
        except Exception:
            # ignore robots failures
            continue

    # Pagination expansion (best effort, bounded)
    for u in _expand_pagination(candidate_urls, MAX_PAGINATION_EXPANSION):
        _add(u)

    investigator = WebsiteInvestigator()
    results = investigator.investigate_multiple_pages(candidate_urls)
    logger.info(f"Results: {json.dumps(results, indent=2, default=str)}")
    results = json.dumps(results, indent=2, default=str)
    return results



if __name__ == "__main__":
    example_single_page("https://yukonbomber.com/robots.txt")