"""
Image EXIF extraction, description generation, and AI-generated image detection.
Adapted from kmap legacy modules; runs standalone without kmap dependencies.
"""
import os
import time
from pathlib import Path

try:
    from bs4 import BeautifulSoup
except ImportError:  # Optional dependency; only needed by HTML/EXIF paths.
    BeautifulSoup = None
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service as ChromeService
    from selenium.webdriver.common.by import By
except ImportError:  # Optional dependency; only needed by browser crawling.
    webdriver = Options = ChromeService = By = None


def _create_driver(headless: bool = True):
    """Create a Chrome driver for Selenium-based crawling."""
    try:
        from webdriver_manager.chrome import ChromeDriverManager

        service = ChromeService(ChromeDriverManager().install())
    except ImportError:
        service = ChromeService()
    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--log-level=3")
    driver = webdriver.Chrome(service=service, options=chrome_options)
    return driver


def _resolve_path(filename: str) -> str:
    """Resolve filename to absolute path. Handles relative paths relative to cwd."""
    if not filename:
        return ""
    p = Path(filename)
    if p.is_absolute():
        return str(p)
    base = os.environ.get("OSINT_UPLOAD_DIR", os.getcwd())
    return str(Path(base) / filename)


def _getEXIFdata(soup):
    def getMetadata(soup, sid):
        div = soup.find("div", {"id": sid})
        if div is None:
            return {}
        tbl = div.find("table", {"class": "uk-table uk-table-responsive uk-table-striped"})
        div = tbl if tbl else div
        dic_EXIF_data = {}
        for tr in div.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 2:
                continue
            s_key = tds[0].get_text().strip().split("\n")[0]
            s_value = tds[1].get_text().strip().split("\n")[0]
            dic_EXIF_data[s_key] = s_value
        return dic_EXIF_data

    return {
        "image": getMetadata(soup, "image"),
        "camera": getMetadata(soup, "camera"),
        "location": getMetadata(soup, "location"),
        "fullmetadata": getMetadata(soup, "full"),
    }


def getEXIFdata(filename: str) -> dict:
    """Extract EXIF metadata from an image file (uses jimpl.com via Selenium)."""
    path = _resolve_path(filename)
    driver = _create_driver(headless=True)
    try:
        driver.get("https://jimpl.com/")
        time.sleep(2)
        input_file = driver.find_element(By.ID, "js-upload-input")
        input_file.send_keys(path)
        time.sleep(5)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        metadata = _getEXIFdata(soup)
        return metadata
    except Exception as e:
        return {"error": str(e), "image": {}, "camera": {}, "location": {}, "fullmetadata": {}}
    finally:
        driver.quit()


def _getDescription(soup):
    div = soup.find("div", {"id": "description-container"})
    if div is None:
        return ""
    p = div.find("p", {"id": "description-text"})
    elem = p if p else div
    return elem.get_text() or ""


def genDescription(filename: str) -> str:
    """Generate image description (uses foundmyself.com via Selenium)."""
    path = _resolve_path(filename)
    driver = _create_driver(headless=True)
    try:
        driver.get("https://www.foundmyself.com/tools/image-description-generator")
        time.sleep(2)
        input_file = driver.find_element(By.XPATH, "//input[@class='dz-hidden-input']")
        input_file.send_keys(path)
        time.sleep(15)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        return _getDescription(soup)
    except Exception as e:
        return f"Error generating description: {e}"
    finally:
        driver.quit()


def _getDetectOutcome(soup):
    div = soup.find("div", {"class": "detection-results-content"})
    if div is None:
        return {}
    results = {}
    for p in div.find_all("div", {"class": "probability-item"}):
        label_el = p.find("span", {"class": "probability-label"})
        value_el = p.find("span", {"class": "probability-value"})
        if label_el and value_el:
            results[label_el.get_text().strip()] = value_el.get_text().strip()
    return results


def detectGenImage(filename: str) -> dict:
    """Detect if an image is AI-generated (uses decopy.ai via Selenium)."""
    path = _resolve_path(filename)
    driver = _create_driver(headless=True)
    try:
        driver.get("https://decopy.ai/ai-image-detector/")
        time.sleep(2)
        input_file = driver.find_element(By.XPATH, "//input[@class='cursor-pointer']")
        input_file.send_keys(path)
        time.sleep(15)
        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        return _getDetectOutcome(soup)
    except Exception as e:
        return {"error": str(e)}
    finally:
        driver.quit()
