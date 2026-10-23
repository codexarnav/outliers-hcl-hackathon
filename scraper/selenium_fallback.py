"""
Selenium fallback module for DTU Scraper.
Used ONLY when static HTTP fetch fails to retrieve JS-rendered listing content.
Kept strictly isolated from core requests-based flow.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class SeleniumFallbackUnavailable(Exception):
    """Raised when Selenium or required WebDriver is not available."""
    pass


class SeleniumFallbackFetcher:
    """Headless browser fallback for pages that require client-side JavaScript execution."""

    def __init__(self, user_agent: Optional[str] = None, headless: bool = True):
        self.user_agent = user_agent
        self.headless = headless

    def fetch_rendered_html(
        self,
        url: str,
        wait_selector: Optional[str] = None,
        timeout: int = 15
    ) -> str:
        """Fetch page content using headless browser after waiting for JavaScript rendering."""
        try:
            from selenium import webdriver
            from selenium.webdriver.chrome.options import Options as ChromeOptions
            from selenium.webdriver.common.by import By
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
        except ImportError as e:
            logger.error("Selenium is not installed: %s", e)
            raise SeleniumFallbackUnavailable("selenium package is not installed") from e

        options = ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--log-level=3")

        if self.user_agent:
            options.add_argument(f"user-agent={self.user_agent}")

        driver = None
        try:
            logger.info("Initializing Selenium WebDriver for fallback fetch of: %s", url)
            driver = webdriver.Chrome(options=options)
            driver.set_page_load_timeout(timeout)
            driver.get(url)

            if wait_selector:
                logger.info("Waiting up to %ds for element '%s' to render...", timeout, wait_selector)
                WebDriverWait(driver, timeout).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, wait_selector))
                )

            html = driver.page_source
            return html
        except Exception as e:
            logger.error("Selenium fallback failed for %s: %s", url, e)
            raise
        finally:
            if driver:
                try:
                    driver.quit()
                except Exception:
                    pass
