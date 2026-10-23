"""
HTTP Fetcher module for DTU Scraper.
Handles politeness, robots.txt compliance, rate-limiting, retries, and circuit breaker.
"""

import logging
import random
import time
import urllib.parse
import urllib.robotparser
from typing import Optional, Dict, Any

import requests

logger = logging.getLogger(__name__)


class CircuitBreakerError(Exception):
    """Raised when consecutive failures reach the configured threshold."""
    pass


class PoliteFetcher:
    """Polite HTTP Fetcher implementing robots.txt compliance, rate limiting with jitter,

    exponential backoff retries, and a circuit breaker.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.user_agent = config.get("user_agent", "DTU-Hackathon-Scraper/1.0")
        self.page_delay_min = float(config.get("page_delay_min", 1.0))
        self.page_delay_max = float(config.get("page_delay_max", 3.0))
        self.pdf_delay_min = float(config.get("pdf_delay_min", 2.0))
        self.pdf_delay_max = float(config.get("pdf_delay_max", 3.0))

        self.connect_timeout = int(config.get("connect_timeout", 10))
        self.read_timeout = int(config.get("read_timeout", 30))
        self.pdf_read_timeout = int(config.get("pdf_read_timeout", 60))

        self.max_retries = int(config.get("max_retries", 3))
        self.backoff_base = float(config.get("backoff_base", 2.0))
        self.retry_status_codes = set(config.get("retry_status_codes", [429, 500, 502, 503, 504]))
        self.circuit_breaker_threshold = int(config.get("circuit_breaker_threshold", 5))

        self.consecutive_failures = 0
        self.last_request_time = 0.0

        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.user_agent})

        self.robot_parser: Optional[urllib.robotparser.RobotFileParser] = None
        self.crawl_delay_from_robots: Optional[float] = None

    def load_robots_txt(self, base_url: str):
        """Fetch and parse robots.txt from base_url."""
        robots_url = urllib.parse.urljoin(base_url, "/robots.txt")
        parser = urllib.robotparser.RobotFileParser()
        try:
            logger.info("Fetching robots.txt from %s", robots_url)
            # Use raw session to avoid recursive delay check on init
            resp = self.session.get(
                robots_url,
                timeout=(self.connect_timeout, self.read_timeout)
            )
            if resp.status_code == 200:
                parser.parse(resp.text.splitlines())
                self.robot_parser = parser
                # Check for crawl-delay
                delay = parser.crawl_delay(self.user_agent)
                if delay is not None:
                    self.crawl_delay_from_robots = float(delay)
                    logger.info("robots.txt specified Crawl-delay: %s seconds", self.crawl_delay_from_robots)
                else:
                    logger.info("robots.txt loaded, no Crawl-delay directive specified.")
            else:
                logger.warning("Could not fetch robots.txt (status %d). Assuming allowed.", resp.status_code)
                self.robot_parser = parser
                parser.parse([])
        except Exception as e:
            logger.warning("Error loading robots.txt from %s: %s. Assuming allowed.", robots_url, e)
            self.robot_parser = parser
            parser.parse([])

    def can_fetch(self, url: str) -> bool:
        """Check whether robots.txt allows fetching the given URL."""
        if self.robot_parser is None:
            return True
        return self.robot_parser.can_fetch(self.user_agent, url)

    def _sleep_polite(self, is_pdf: bool = False):
        """Enforce sequential delay with random jitter between requests."""
        now = time.time()
        elapsed = now - self.last_request_time

        if self.crawl_delay_from_robots is not None:
            delay = self.crawl_delay_from_robots + random.uniform(0.5, 1.5)
        elif is_pdf:
            delay = random.uniform(self.pdf_delay_min, self.pdf_delay_max)
        else:
            delay = random.uniform(self.page_delay_min, self.page_delay_max)

        remaining = delay - elapsed
        if remaining > 0:
            logger.debug("Polite sleep: waiting %.2f seconds", remaining)
            time.sleep(remaining)

        self.last_request_time = time.time()

    def get(self, url: str, stream: bool = False, is_pdf: bool = False) -> requests.Response:
        """Perform a polite GET request with retries, exponential backoff,

        and circuit breaker monitoring.
        """
        if not self.can_fetch(url):
            raise PermissionError(f"robots.txt disallows fetching {url}")

        if self.consecutive_failures >= self.circuit_breaker_threshold:
            raise CircuitBreakerError(
                f"Circuit breaker tripped: {self.consecutive_failures} consecutive failures."
            )

        read_timeout = self.pdf_read_timeout if is_pdf else self.read_timeout
        timeouts = (self.connect_timeout, read_timeout)

        attempt = 0
        while True:
            self._sleep_polite(is_pdf=is_pdf)
            try:
                logger.debug("GET %s (attempt %d/%d)", url, attempt + 1, self.max_retries + 1)
                resp = self.session.get(url, stream=stream, timeout=timeouts)

                if resp.status_code in self.retry_status_codes:
                    logger.warning("Received status %d from %s", resp.status_code, url)
                    if attempt < self.max_retries:
                        attempt += 1
                        backoff = self.backoff_base ** attempt
                        logger.info("Backing off for %.2f seconds before retry...", backoff)
                        time.sleep(backoff)
                        continue
                    else:
                        self.consecutive_failures += 1
                        logger.error("Max retries exceeded for %s with status %d", url, resp.status_code)
                        if self.consecutive_failures >= self.circuit_breaker_threshold:
                            raise CircuitBreakerError(
                                f"Circuit breaker tripped after {self.consecutive_failures} failures."
                            )
                        return resp

                # Success or non-retryable response
                if 200 <= resp.status_code < 400:
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures += 1
                    if self.consecutive_failures >= self.circuit_breaker_threshold:
                        raise CircuitBreakerError(
                            f"Circuit breaker tripped after {self.consecutive_failures} failures."
                        )

                return resp

            except (requests.RequestException, requests.Timeout) as e:
                logger.warning("Request error for %s: %s", url, e)
                if attempt < self.max_retries:
                    attempt += 1
                    backoff = self.backoff_base ** attempt
                    logger.info("Backing off for %.2f seconds before retry...", backoff)
                    time.sleep(backoff)
                else:
                    self.consecutive_failures += 1
                    logger.error("Max retries exceeded for %s. Consecutive failures: %d", url, self.consecutive_failures)
                    if self.consecutive_failures >= self.circuit_breaker_threshold:
                        raise CircuitBreakerError(
                            f"Circuit breaker tripped after {self.consecutive_failures} failures."
                        ) from e
                    raise

    def head(self, url: str) -> requests.Response:
        """Perform a polite HEAD request."""
        if not self.can_fetch(url):
            raise PermissionError(f"robots.txt disallows fetching {url}")

        self._sleep_polite(is_pdf=True)
        timeouts = (self.connect_timeout, self.read_timeout)
        try:
            resp = self.session.head(url, timeout=timeouts)
            return resp
        except Exception as e:
            logger.warning("HEAD request failed for %s: %s", url, e)
            raise
