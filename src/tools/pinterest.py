"""
Pinterest Profile Scraper & Image Downloader
Selenium-based scraper to handle Pinterest's anti-scraping measures
"""

from agent.tool_decorator import tool
import hashlib
import json
import logging
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PinterestSeleniumScraper:
    """
    Scrape Pinterest using Selenium (handles JavaScript)
    Requires: pip install selenium
    Download ChromeDriver: https://chromedriver.chromium.org/
    """
    
    def __init__(self, headless: bool = True, slow_scroll: bool = True):
        """
        Args:
            headless: Run browser in background
            slow_scroll: Slower scrolling to avoid detection
        """
        self.headless = headless
        self.slow_scroll = slow_scroll
        self.driver = None
        self._setup_driver()
    
    def _setup_driver(self):
        """Setup Chrome driver with anti-detection measures"""
        chrome_options = Options()
        
        if self.headless:
            chrome_options.add_argument('--headless')
        
        # Anti-detection settings
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-gpu')
        chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # Disable automation flags
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        self.driver = webdriver.Chrome(options=chrome_options)
        
        # Execute CDP commands to hide automation
        self.driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
            'source': '''
                Object.defineProperty(navigator, 'webdriver', {
                    get: () => undefined
                })
            '''
        })
    
    def scrape_profile(self, username: str, max_pins: int = 100, max_find_time_in_seconds: int = 10) -> List[Dict]:
        """
        Scrape pins from a Pinterest profile
        
        Args:
            username: Pinterest username
            max_pins: Maximum number of pins to scrape
        
        Returns:
            List of pin data dictionaries
        """
        url = f"https://www.pinterest.com/{username}/"
        logger.info(f"Scraping profile: {url}")
        
        self.driver.get(url)
        time.sleep(3)  # Wait for initial load
        
        pins = []
        pins_without_scraped_at = []
        last_height = 0
        scroll_attempts = 0
        max_scroll_attempts = 2
        start_time = time.time()
        while len(pins) < max_pins and scroll_attempts < max_scroll_attempts and time.time() - start_time < max_find_time_in_seconds:
            # Scroll down to load more pins
            self._scroll_page()
            
            # Extract pins from current view
            pin_elements = self.driver.find_elements(By.CSS_SELECTOR, '[data-test-id="pin"]')
            
            for elem in pin_elements:
                if len(pins) >= max_pins:
                    break
                
                try:
                    pin_data = self._extract_pin_data(elem)
                    pin_data_without_scraped_at = pin_data.copy()
                    pin_data_without_scraped_at.pop('scraped_at')

                    if pin_data_without_scraped_at not in pins_without_scraped_at:
                        pins_without_scraped_at.append(pin_data_without_scraped_at)
                        pins.append(pin_data)
                        start_time = time.time()
                        logger.info(f"Found pin {len(pins)}/{max_pins}")
                except Exception as e:
                    logger.debug(f"Error extracting pin: {e}")
                    continue
            
            # Check if we've reached the bottom
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                scroll_attempts += 1
            else:
                scroll_attempts = 0
                last_height = new_height
            
            time.sleep(2 if self.slow_scroll else 1)
        
        logger.info(f"✓ Scraped {len(pins)} pins")
        return pins
    
    def _scroll_page(self):
        """Scroll page to load more content"""
        if self.slow_scroll:
            # Slow, natural-looking scroll
            scroll_pause = 0.5
            current_scroll = 0
            scroll_increment = 300
            
            for _ in range(3):
                current_scroll += scroll_increment
                self.driver.execute_script(f"window.scrollTo(0, {current_scroll});")
                time.sleep(scroll_pause)
        else:
            # Fast scroll
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
    
    def _extract_pin_data(self, element) -> Optional[Dict]:
        """Extract data from a pin element"""
        try:
            # Try to find image
            img = element.find_element(By.TAG_NAME, 'img')
            image_url = img.get_attribute('src')
            
            # Get high-res version (replace size parameters)
            if 'pinimg.com' in image_url:
                # Pinterest uses URL patterns like /236x/, /474x/, etc.
                # Replace with originals for highest quality
                image_url = re.sub(r'/\d+x/', '/originals/', image_url)
            
            # Try to get link
            try:
                link_elem = element.find_element(By.TAG_NAME, 'a')
                pin_url = link_elem.get_attribute('href')
            except:
                pin_url = None
            
            # Try to get description
            try:
                desc_elem = element.find_element(By.CSS_SELECTOR, '[data-test-id="desc"]')
                description = desc_elem.text
            except:
                description = img.get_attribute('alt') or ''
            
            return {
                'image_url': image_url,
                'pin_url': pin_url,
                'description': description,
                'scraped_at': datetime.now().isoformat()
            }
            
        except Exception as e:
            logger.debug(f"Could not extract pin data: {e}")
            return None
    
    def download_pins(self, pins: List[Dict], output_dir: str = "downloads/pinterest"):
        """Download images from pins"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        
        downloaded = []
        
        for i, pin in enumerate(pins):
            image_url = pin.get('image_url')
            if not image_url:
                continue
            
            try:
                response = requests.get(image_url, stream=True, timeout=10)
                response.raise_for_status()
                
                # Generate filename
                url_hash = hashlib.md5(image_url.encode()).hexdigest()[:8]
                ext = Path(urlparse(image_url).path).suffix or '.jpg'
                filename = f"pin_{i+1:04d}_{url_hash}{ext}"
                filepath = Path(output_dir) / filename
                
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"✓ Downloaded {i+1}/{len(pins)}: {filepath}")
                downloaded.append(str(filepath))
                
                # Save metadata
                meta_path = filepath.with_suffix('.json')
                with open(meta_path, 'w') as f:
                    json.dump(pin, f, indent=2)
                
            except Exception as e:
                logger.error(f"Failed to download {image_url}: {e}")
        
        return downloaded
    
    def close(self):
        """Close browser"""
        if self.driver:
            self.driver.quit()
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()


# ==================================================
# USAGE EXAMPLES
# ==================================================

def scrape_pinterest_profile(username: str, max_pins: int = 50, output_dir: str = "evidence/pinterest/"):
    """
    Main function to scrape a Pinterest profile using Selenium
    
    Args:
        username: Pinterest username to scrape
        max_pins: Maximum number of pins to scrape
        output_dir: Directory to save downloaded images
    
    Returns:
        Dict containing scraped data and downloaded file paths
    """
    result = {
        'username': username,
        'timestamp': datetime.now().isoformat(),
        'pins': [],
        'images_downloaded': [],
        'errors': []
    }
    
    try:
        with PinterestSeleniumScraper(headless=True) as scraper:
            # Scrape profile
            pins = scraper.scrape_profile(
                username=username,
                max_pins=max_pins
            )
            
            result['pins'] = pins
            logger.info(f"Found {len(pins)} pins")
            
            # Download images
            downloaded = scraper.download_pins(
                pins,
                output_dir=f"{output_dir}/{username}"
            )
            
            result['images_downloaded'] = downloaded
            logger.info(f"Downloaded {len(downloaded)} images")
            
    except Exception as e:
        logger.error(f"Scraping failed: {e}")
        result['errors'].append(str(e))
    
    return result

@tool
def pinterest_scrape_by_username(username: str) -> str:
    """Scrape a Pinterest profile by username, input the username of the Pinterest profile to scrape.
    To find the username of the Pinterest profile, you can use the engine_search tool to search the web for information about the object of investigation.
    Args:
        username: The username of the Pinterest profile to scrape.
        
    Returns:
        Something with the information of the Pinterest profile.
    """
    logger.info(f"Scraping a Pinterest profile by username: {username}")
    scraper = PinterestSeleniumScraper()
    results = scraper.scrape_profile(username)
    logger.info(f"Results: {json.dumps(results, indent=2, default=str)}")
    return json.dumps(results, indent=2, default=str)

if __name__ == "__main__":
    # Example usage
    username = "gouldieloxx"  # Replace with target username
    result = scrape_pinterest_profile(username, max_pins=20)
    
    print(f"Scraped {len(result['pins'])} pins")
    print(f"Downloaded {len(result['images_downloaded'])} images")
    
    if result['errors']:
        print(f"Errors: {result['errors']}")
    
    # Save report
    with open('pinterest_report.json', 'w') as f:
        json.dump(result, f, indent=2)