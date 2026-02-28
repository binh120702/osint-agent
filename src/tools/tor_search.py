"""
Tor/Onion Site Access for OSINT Investigations
IMPORTANT: Only use for legal investigations with proper authorization
"""

import requests
from stem import Signal
from stem.control import Controller
import socks
import socket
from typing import Dict, Optional, List
import time
import logging
from pathlib import Path
import json
from datetime import datetime
from bs4 import BeautifulSoup
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# ==================================================
# METHOD 1: Using Tor SOCKS Proxy (Recommended)
# ==================================================

class TorSession:
    """
    Access Tor network via SOCKS proxy
    
    Prerequisites:
    1. Install Tor Browser or Tor service
       - Windows/Mac: https://www.torproject.org/download/
       - Linux: sudo apt-get install tor
    2. Start Tor service (usually on port 9050 or 9150)
    3. Install Python packages: pip install requests[socks] stem
    """
    
    def __init__(
        self,
        tor_proxy_host: str = '127.0.0.1',
        tor_proxy_port: int = 9150,  # 9150 for Tor Browser
        control_port: int = 9051,
        control_password: Optional[str] = None
    ):
        self.tor_proxy_host = tor_proxy_host
        self.tor_proxy_port = tor_proxy_port
        self.control_port = control_port
        self.control_password = control_password
        
        # Create session with Tor SOCKS proxy
        self.session = requests.Session()
        self.session.proxies = {
            'http': f'socks5h://{tor_proxy_host}:{tor_proxy_port}',
            'https': f'socks5h://{tor_proxy_host}:{tor_proxy_port}'
        }
        
        # Set headers to avoid fingerprinting
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; rv:102.0) Gecko/20100101 Firefox/102.0',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        })
    
    def test_connection(self) -> bool:
        """Test if Tor connection is working"""
        try:
            # Check public IP via Tor
            response = self.session.get('https://check.torproject.org/api/ip', timeout=30)
            data = response.json()
            
            if data.get('IsTor'):
                logger.info(f"✓ Connected to Tor network")
                logger.info(f"  Your IP: {data.get('IP')}")
                return True
            else:
                logger.error("✗ Not connected to Tor network")
                return False
                
        except Exception as e:
            logger.error(f"✗ Tor connection test failed: {e}")
            logger.info("Make sure Tor service is running:")
            logger.info("  - Linux: sudo service tor start")
            logger.info("  - Windows/Mac: Open Tor Browser")
            return False
    
    def fetch_onion(self, url: str, timeout: int = 30) -> Dict:
        """
        Fetch an onion site
        
        Args:
            url: .onion URL (e.g., 'http://example.onion')
            timeout: Request timeout in seconds (onion sites are slow)
        
        Returns:
            Dict with response data
        """
        try:
            logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=timeout)
            
            return {
                'success': True,
                'url': url,
                'status_code': response.status_code,
                'html': response.text,
                'headers': dict(response.headers),
                'content': response.content,
                'timestamp': datetime.now().isoformat()
            }
            
        except requests.exceptions.Timeout:
            logger.error(f"Timeout accessing {url}")
            return {'success': False, 'error': 'Timeout'}
            
        except requests.exceptions.ConnectionError as e:
            logger.error(f"Connection error: {e}")
            return {'success': False, 'error': 'Connection failed - check Tor service'}
            
        except Exception as e:
            logger.error(f"Error: {e}")
            return {'success': False, 'error': str(e)}
    
    def renew_circuit(self):
        """
        Get new Tor circuit (new IP address)
        Requires Tor control port access
        """
        try:
            with Controller.from_port(port=self.control_port) as controller:
                if self.control_password:
                    controller.authenticate(password=self.control_password)
                else:
                    controller.authenticate()
                
                controller.signal(Signal.NEWNYM)
                logger.info("✓ Tor circuit renewed (new IP)")
                time.sleep(5)  # Wait for new circuit
                
        except Exception as e:
            logger.warning(f"Could not renew circuit: {e}")
            logger.info("To enable circuit renewal:")
            logger.info("  1. Edit /etc/tor/torrc (Linux) or Tor config")
            logger.info("  2. Add: ControlPort 9051")
            logger.info("  3. Add: HashedControlPassword <hash>")
            logger.info("  4. Restart Tor service")


# ==================================================
# METHOD 2: Using Tor Binary Directly
# ==================================================

class TorController:
    """
    Start and control Tor process programmatically
    Requires: pip install stem
    """
    
    def __init__(self, tor_path: Optional[str] = None):
        """
        Args:
            tor_path: Path to Tor binary (auto-detected if None)
        """
        self.tor_path = tor_path or self._find_tor()
        self.process = None
    
    def _find_tor(self) -> str:
        """Find Tor binary on system"""
        common_paths = [
            '/usr/bin/tor',
            '/usr/local/bin/tor',
            'C:\\Program Files\\Tor Browser\\Browser\\TorBrowser\\Tor\\tor.exe',
            'C:\\Program Files (x86)\\Tor Browser\\Browser\\TorBrowser\\Tor\\tor.exe'
        ]
        
        for path in common_paths:
            if Path(path).exists():
                return path
        
        raise FileNotFoundError("Tor binary not found. Install Tor Browser or tor package.")
    
    def start(self, socks_port: int = 9050, control_port: int = 9051):
        """Start Tor process"""
        from stem.process import launch_tor_with_config
        
        try:
            logger.info("Starting Tor process...")
            self.process = launch_tor_with_config(
                config={
                    'SocksPort': str(socks_port),
                    'ControlPort': str(control_port),
                },
                tor_cmd=self.tor_path
            )
            logger.info(f"✓ Tor started on SOCKS port {socks_port}")
            
        except Exception as e:
            logger.error(f"Failed to start Tor: {e}")
            raise
    
    def stop(self):
        """Stop Tor process"""
        if self.process:
            self.process.kill()
            logger.info("✓ Tor stopped")


# ==================================================
# METHOD 3: Using Tor2Web Proxy (Not Recommended)
# ==================================================

class Tor2WebProxy:
    """
    Access .onion sites via Tor2Web gateways (clearnet)
    
    WARNING: 
    - NOT anonymous (your real IP is visible)
    - Gateway operator can see all traffic
    - Only use for non-sensitive investigations
    - Many onion sites block Tor2Web
    """
    
    GATEWAYS = [
        'onion.ly',
        'onion.ws',
        'tor2web.org'
    ]
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def fetch_via_gateway(self, onion_url: str, gateway: Optional[str] = None) -> Dict:
        """
        Fetch onion site via Tor2Web gateway
        
        Args:
            onion_url: Original .onion URL
            gateway: Gateway to use (auto-select if None)
        """
        # Remove .onion and protocol
        onion_address = onion_url.replace('http://', '').replace('https://', '').replace('.onion', '')
        
        if not gateway:
            gateway = self.GATEWAYS[0]
        
        clearnet_url = f"https://{onion_address}.{gateway}"
        
        logger.warning(f"⚠️  Using Tor2Web gateway (NOT ANONYMOUS)")
        logger.info(f"Fetching: {clearnet_url}")
        
        try:
            response = self.session.get(clearnet_url, timeout=30)
            return {
                'success': True,
                'url': clearnet_url,
                'original_onion': onion_url,
                'status_code': response.status_code,
                'html': response.text,
                'warning': 'Accessed via Tor2Web - NOT ANONYMOUS',
                'timestamp': datetime.now().isoformat()
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}


# ==================================================
# ONION SITE PARSER
# ==================================================

class OnionSiteParser:
    """Parse and extract data from onion sites"""
    
    def __init__(self, url: str):
        self.url = url
    
    def parse(self, html: str) -> Dict:
        """Parse onion site HTML"""
        soup = BeautifulSoup(html, 'html.parser')
        
        return {
            'url': self.url,
            'title': self._get_title(soup),
            'text_content': self._get_text(soup),
            'links': self._get_links(soup),
            'images': self._get_images(soup),
            'emails': self._extract_emails(html),
            'bitcoin_addresses': self._extract_bitcoin(html),
            'pgp_keys': self._extract_pgp(html),
            'timestamp': datetime.now().isoformat()
        }
    
    def _get_title(self, soup: BeautifulSoup) -> str:
        title = soup.find('title')
        return title.string if title else ''
    
    def _get_text(self, soup: BeautifulSoup) -> str:
        # Remove scripts and styles
        for tag in soup(['script', 'style']):
            tag.decompose()
        return soup.get_text(separator=' ', strip=True)
    
    def _get_links(self, soup: BeautifulSoup) -> List[str]:
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            if href.endswith('.onion') or '.onion/' in href:
                links.append(href)
        return links
    
    def _get_images(self, soup: BeautifulSoup) -> List[str]:
        return [img.get('src', '') for img in soup.find_all('img')]
    
    def _extract_emails(self, html: str) -> List[str]:
        import re
        pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
        return list(set(re.findall(pattern, html)))
    
    def _extract_bitcoin(self, html: str) -> List[str]:
        import re
        # Bitcoin address pattern
        pattern = r'\b[13][a-km-zA-HJ-NP-Z1-9]{25,34}\b'
        return list(set(re.findall(pattern, html)))
    
    def _extract_pgp(self, html: str) -> List[str]:
        import re
        pgp_blocks = re.findall(
            r'-----BEGIN PGP.*?-----END PGP.*?-----',
            html,
            re.DOTALL
        )
        return pgp_blocks


# ==================================================
# COMPLETE ONION INVESTIGATOR
# ==================================================

class OnionInvestigator:
    """Complete investigation tool for onion sites"""
    
    def __init__(self, use_tor2web: bool = False):
        """
        Args:
            use_tor2web: If True, use Tor2Web (not anonymous)
                        If False, use local Tor (anonymous)
        """
        if use_tor2web:
            self.client = Tor2WebProxy()
            self.is_anonymous = False
        else:
            self.client = TorSession()
            self.is_anonymous = True
            
            # Test Tor connection
            if not self.client.test_connection():
                raise ConnectionError("Tor connection failed. Start Tor service first.")
    
    def investigate(self, onion_url: str, save_evidence: bool = True) -> Dict:
        """
        Investigate an onion site
        
        Args:
            onion_url: The .onion URL to investigate
            save_evidence: Save HTML and report to disk
        
        Returns:
            Dict with investigation results
        """
        logger.info(f"Starting investigation: {onion_url}")
        
        # Fetch site
        if self.is_anonymous:
            response = self.client.fetch_onion(onion_url)
        else:
            response = self.client.fetch_via_gateway(onion_url)
        
        if not response.get('success'):
            return {
                'error': response.get('error'),
                'url': onion_url,
                'timestamp': datetime.now().isoformat()
            }
        
        # Parse content
        parser = OnionSiteParser(onion_url)
        data = parser.parse(response['html'])
        
        # Add metadata
        data['status_code'] = response['status_code']
        data['is_anonymous_access'] = self.is_anonymous
        data['headers'] = response.get('headers', {})
        
        # Save evidence
        if save_evidence:
            self._save_evidence(onion_url, response['html'], data)
        
        return data
    
    def _save_evidence(self, url: str, html: str, data: Dict):
        """Save investigation evidence"""
        # Create evidence directory
        evidence_dir = Path('evidence/onion_sites')
        evidence_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate filename from onion address
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        base_name = f"{timestamp}_{url_hash}"
        
        # Save HTML
        html_path = evidence_dir / f"{base_name}.html"
        with open(html_path, 'w', encoding='utf-8') as f:
            f.write(html)
        
        # Save parsed data
        json_path = evidence_dir / f"{base_name}_report.json"
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, default=str)
        
        logger.info(f"✓ Evidence saved:")
        logger.info(f"  HTML: {html_path}")
        logger.info(f"  Report: {json_path}")


# ==================================================
# USAGE EXAMPLES
# ==================================================

def example_tor_session():
    """Example: Using local Tor (anonymous)"""
    
    # Create Tor session
    tor = TorSession(
        tor_proxy_port=9050,  # Use 9150 if using Tor Browser
    )
    
    # Test connection
    if not tor.test_connection():
        print("ERROR: Tor not running!")
        print("Start Tor:")
        print("  Linux: sudo service tor start")
        print("  Windows/Mac: Open Tor Browser")
        return
    
    # Fetch an onion site
    response = tor.fetch_onion('http://example.onion')
    
    if response['success']:
        print(f"Status: {response['status_code']}")
        print(f"HTML length: {len(response['html'])}")
    else:
        print(f"Error: {response['error']}")


def example_complete_investigation():
    """Example: Complete onion site investigation"""
    
    try:
        # Create investigator (requires Tor running)
        investigator = OnionInvestigator(use_tor2web=False)
        
        # Investigate site
        result = investigator.investigate(
            onion_url='http://example.onion',
            save_evidence=True
        )
        
        # Print results
        print("\n" + "="*50)
        print("INVESTIGATION RESULTS")
        print("="*50)
        print(f"Title: {result.get('title')}")
        print(f"Bitcoin addresses: {result.get('bitcoin_addresses')}")
        print(f"Emails: {result.get('emails')}")
        print(f"Links found: {len(result.get('links', []))}")
        print(f"Evidence saved: Yes")
        
    except ConnectionError as e:
        print(f"ERROR: {e}")
        print("\nTo fix:")
        print("1. Install Tor: https://www.torproject.org/download/")
        print("2. Start Tor service")
        print("3. Run this script again")


def example_tor2web():
    """Example: Using Tor2Web (NOT anonymous)"""
    
    print("⚠️  WARNING: Using Tor2Web - NOT ANONYMOUS")
    
    investigator = OnionInvestigator(use_tor2web=True)
    result = investigator.investigate(
        onion_url='http://ciadotgov4sjwlzihbbgxnqg3xiyrg7so2r2o3lt5wz5ypk4sxyjstad.onion',
        save_evidence=True
    )
    
    print(json.dumps(result, indent=2, default=str))


def setup_instructions():
    """Print setup instructions"""
    print("""
    ╔══════════════════════════════════════════════════════════╗
    ║        TOR SETUP INSTRUCTIONS FOR OSINT                  ║
    ╚══════════════════════════════════════════════════════════╝
    
    1. INSTALL TOR:
       • Windows/Mac: Download Tor Browser
         https://www.torproject.org/download/
       
       • Linux: 
         sudo apt-get update
         sudo apt-get install tor
    
    2. START TOR SERVICE:
       • Linux:
         sudo service tor start
         sudo service tor status
       
       • Windows/Mac:
         Open Tor Browser (runs Tor automatically)
    
    3. INSTALL PYTHON DEPENDENCIES:
       pip install requests[socks] stem pysocks
    
    4. VERIFY TOR IS RUNNING:
       • Check if port 9050 is listening
         Linux: sudo netstat -tlnp | grep 9050
         Windows: netstat -an | findstr 9050
    
    5. TEST CONNECTION:
       python this_script.py
    
    ⚠️  IMPORTANT NOTES:
    • Always use VPN + Tor for sensitive investigations
    • Respect local laws and regulations
    • Only investigate with proper authorization
    • Document everything for legal compliance
    • Never access illegal content
    
    PORTS:
    • Tor SOCKS Proxy: 9050 (service) or 9150 (Tor Browser)
    • Tor Control Port: 9051
    """)


if __name__ == "__main__":
    # Show setup instructions
    # setup_instructions()
    
    # Run example
    # example_tor_session()
    # example_complete_investigation()
    example_tor2web()