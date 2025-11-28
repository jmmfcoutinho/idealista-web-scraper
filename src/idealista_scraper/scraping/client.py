"""HTTP client abstraction for Bright Data and other backends."""

from __future__ import annotations

import time
from typing import Protocol

import requests
from playwright.sync_api import sync_playwright

from idealista_scraper.config import ScrapingConfig, get_brightdata_credentials
from idealista_scraper.utils.billing import get_bandwidth_tracker
from idealista_scraper.utils.logging import get_logger
from idealista_scraper.utils.time_utils import retry_with_backoff, sleep_with_jitter

logger = get_logger(__name__)


# Wait selectors by page type (from html/zyte/FINDINGS.md)
WAIT_SELECTOR_HOMEPAGE = "nav.locations-list"
WAIT_SELECTOR_DISTRICT_CONCELHOS = "section.municipality-search"
WAIT_SELECTOR_SEARCH_RESULTS = "article.item"
WAIT_SELECTOR_LISTING_DETAIL = "section.detail-info"


class PageClient(Protocol):
    """Protocol for fetching HTML pages.

    Implementations may use Bright Data, httpx, requests, etc.
    """

    def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Return the HTML content for the given URL.

        Args:
            url: The URL to fetch.
            wait_selector: Optional CSS selector to wait for (for JS-rendered pages).

        Returns:
            The HTML content of the page.

        Raises:
            RuntimeError: If the page could not be fetched.
        """
        ...


class BrightDataClientError(Exception):
    """Exception raised when Bright Data returns an error."""

    def __init__(
        self,
        message: str,
        is_connection_error: bool = False,
    ) -> None:
        """Initialize BrightDataClientError.

        Args:
            message: Error message.
            is_connection_error: Whether this is a connection error.
        """
        super().__init__(message)
        self.is_connection_error = is_connection_error


class BrightDataClient:
    """Bright Data Scraping Browser client for fetching JavaScript-rendered HTML pages.

    Uses Bright Data's Scraping Browser via Playwright to render pages with JavaScript,
    which is required for Idealista content.

    Attributes:
        browser_user: The Bright Data browser zone username.
        browser_pass: The Bright Data browser zone password.
        config: Scraping configuration for delays and retries.
    """

    BROWSER_HOST = "brd.superproxy.io"
    BROWSER_PORT = 9222
    DEFAULT_TIMEOUT = 120_000  # 2 minutes for page load
    WAIT_TIMEOUT = 30_000  # 30 seconds for selector wait

    def __init__(
        self,
        browser_user: str | None = None,
        browser_pass: str | None = None,
        config: ScrapingConfig | None = None,
    ) -> None:
        """Initialize the Bright Data client.

        Args:
            browser_user: Bright Data browser username. If None, reads from env.
            browser_pass: Bright Data browser password. If None, reads from env.
            config: Scraping configuration. Uses defaults if None.
        """
        if browser_user is None or browser_pass is None:
            creds = get_brightdata_credentials()
            browser_user = browser_user or creds["user"]
            browser_pass = browser_pass or creds["password"]

        self.browser_user = browser_user
        self.browser_pass = browser_pass
        self.config = config or ScrapingConfig()
        self._request_count = 0
        self._browser_ws = (
            f"wss://{self.browser_user}:{self.browser_pass}"
            f"@{self.BROWSER_HOST}:{self.BROWSER_PORT}"
        )

    def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Fetch HTML content from a URL using Bright Data Scraping Browser.

        Args:
            url: The URL to fetch.
            wait_selector: Optional CSS selector to wait for before returning.
                This helps ensure dynamic content is loaded.

        Returns:
            The rendered HTML content of the page.

        Raises:
            RuntimeError: If the page could not be fetched after retries.
            BrightDataClientError: If Bright Data returns a specific error.
        """
        # Add delay between requests (except for the first)
        if self._request_count > 0:
            sleep_with_jitter(self.config.delay_seconds)
        self._request_count += 1

        def fetch() -> str:
            return self._fetch_with_brightdata(url, wait_selector)

        try:
            return retry_with_backoff(
                func=fetch,
                max_retries=self.config.max_retries,
                base_delay=2.0,
                max_delay=60.0,
                retryable_exceptions=(BrightDataClientError,),
            )
        except BrightDataClientError as e:
            msg = f"Failed to fetch {url} after {self.config.max_retries} retries: {e}"
            raise RuntimeError(msg) from e

    def _fetch_with_brightdata(self, url: str, wait_selector: str | None) -> str:
        """Make a single request to Bright Data Scraping Browser.

        Args:
            url: The URL to fetch.
            wait_selector: Optional CSS selector to wait for.

        Returns:
            The rendered HTML content.

        Raises:
            BrightDataClientError: If Bright Data returns an error.
        """
        logger.debug("Fetching URL via Bright Data: %s (wait: %s)", url, wait_selector)
        start_time = time.time()

        try:
            with sync_playwright() as p:
                logger.debug("Connecting to Bright Data Scraping Browser...")
                browser = p.chromium.connect_over_cdp(self._browser_ws)

                try:
                    page = browser.new_page()
                    page.goto(
                        url, timeout=self.DEFAULT_TIMEOUT, wait_until="domcontentloaded"
                    )

                    if wait_selector:
                        try:
                            page.wait_for_selector(
                                wait_selector, timeout=self.WAIT_TIMEOUT
                            )
                            logger.debug("Selector '%s' found", wait_selector)
                        except Exception as e:
                            # Log but don't fail - page may still have content
                            logger.warning(
                                "Selector '%s' not found within timeout: %s",
                                wait_selector,
                                e,
                            )

                    html = page.content()
                    duration = time.time() - start_time

                    # Record bandwidth for cost tracking
                    html_bytes = len(html.encode("utf-8"))
                    tracker = get_bandwidth_tracker()
                    stats = tracker.record_request(
                        url=url,
                        bytes_received=html_bytes,
                        duration_seconds=duration,
                    )

                    logger.debug(
                        "Fetched %d bytes from %s in %.1fs (est. cost: $%.4f)",
                        html_bytes,
                        url,
                        duration,
                        stats.estimated_cost,
                    )
                    return html

                finally:
                    browser.close()

        except Exception as e:
            error_msg = str(e)
            is_connection = (
                "connect" in error_msg.lower() or "websocket" in error_msg.lower()
            )
            msg = f"Bright Data error for {url}: {error_msg}"
            logger.warning(msg)
            raise BrightDataClientError(msg, is_connection_error=is_connection) from e


class RequestsClient:
    """Simple requests-based client for local development.

    Warning: This client does not render JavaScript, so it will not work
    for Idealista pages that require JS rendering. Use BrightDataClient for
    production scraping.

    Attributes:
        config: Scraping configuration for delays and retries.
    """

    def __init__(self, config: ScrapingConfig | None = None) -> None:
        """Initialize the requests client.

        Args:
            config: Scraping configuration. Uses defaults if None.
        """
        self.config = config or ScrapingConfig()
        self._request_count = 0
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "pt-PT,pt;q=0.9,en;q=0.8",
            }
        )

    def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Fetch HTML content from a URL using requests.

        Note: The wait_selector parameter is ignored as this client
        does not support JavaScript rendering.

        Args:
            url: The URL to fetch.
            wait_selector: Ignored - included for interface compatibility.

        Returns:
            The HTML content of the page.

        Raises:
            RuntimeError: If the page could not be fetched after retries.
        """
        # Add delay between requests (except for the first)
        if self._request_count > 0:
            sleep_with_jitter(self.config.delay_seconds)
        self._request_count += 1

        if wait_selector:
            logger.warning(
                "RequestsClient ignores wait_selector - use BrightDataClient for JS"
            )

        def fetch() -> str:
            response = self._session.get(url, timeout=30)
            response.raise_for_status()
            return response.text

        try:
            return retry_with_backoff(
                func=fetch,
                max_retries=self.config.max_retries,
                base_delay=2.0,
                max_delay=60.0,
                retryable_exceptions=(requests.RequestException,),
            )
        except requests.RequestException as e:
            msg = f"Failed to fetch {url} after {self.config.max_retries} retries: {e}"
            raise RuntimeError(msg) from e


def create_client(config: ScrapingConfig) -> PageClient:
    """Create a page client based on configuration.

    Args:
        config: Scraping configuration that determines which client to use.

    Returns:
        A PageClient instance (BrightDataClient if use_brightdata is True,
        else RequestsClient).
    """
    if config.use_brightdata:
        return BrightDataClient(config=config)
    return RequestsClient(config=config)
