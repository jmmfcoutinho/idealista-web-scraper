"""Async HTTP client for Bright Data Scraping Browser."""

from __future__ import annotations

import time
from typing import Protocol

from playwright.async_api import async_playwright

from idealista_scraper.config import ScrapingConfig, get_brightdata_credentials
from idealista_scraper.utils.async_time_utils import (
    async_retry_with_backoff,
    async_sleep_with_jitter,
)
from idealista_scraper.utils.billing import get_bandwidth_tracker
from idealista_scraper.utils.logging import get_logger

logger = get_logger(__name__)


class AsyncPageClient(Protocol):
    """Protocol for async page fetching.

    Implementations must provide async get_html and close methods.
    """

    async def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Fetch HTML content asynchronously.

        Args:
            url: The URL to fetch.
            wait_selector: Optional CSS selector to wait for (for JS-rendered pages).

        Returns:
            The HTML content of the page.
        """
        ...

    async def close(self) -> None:
        """Clean up resources."""
        ...


class AsyncBrightDataClientError(Exception):
    """Exception raised when Bright Data returns an error."""

    def __init__(self, message: str, is_connection_error: bool = False) -> None:
        """Initialize AsyncBrightDataClientError.

        Args:
            message: Error message.
            is_connection_error: Whether this is a connection error.
        """
        super().__init__(message)
        self.is_connection_error = is_connection_error


class AsyncBrightDataClient:
    """Async Bright Data Scraping Browser client.

    Each call to get_html() creates a new browser connection for better
    IP rotation and isolation. Concurrency is controlled externally via
    semaphore.

    Attributes:
        browser_user: The Bright Data browser zone username.
        browser_pass: The Bright Data browser zone password.
        config: Scraping configuration for delays and retries.
    """

    BROWSER_HOST = "brd.superproxy.io"
    BROWSER_PORT = 9222
    DEFAULT_TIMEOUT = 120_000  # 2 minutes
    WAIT_TIMEOUT = 30_000  # 30 seconds

    def __init__(
        self,
        browser_user: str | None = None,
        browser_pass: str | None = None,
        config: ScrapingConfig | None = None,
    ) -> None:
        """Initialize the async Bright Data client.

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

    async def get_html(self, url: str, wait_selector: str | None = None) -> str:
        """Fetch HTML content from a URL using async Playwright.

        Creates a new browser connection for each request to enable
        better IP rotation when running concurrently.

        Args:
            url: The URL to fetch.
            wait_selector: Optional CSS selector to wait for before returning.
                This helps ensure dynamic content is loaded.

        Returns:
            The rendered HTML content of the page.

        Raises:
            RuntimeError: If the page could not be fetched after retries.
        """
        # Add delay between requests (jitter for anti-detection)
        if self._request_count > 0:
            await async_sleep_with_jitter(self.config.delay_seconds)
        self._request_count += 1

        async def fetch() -> str:
            return await self._fetch_with_brightdata(url, wait_selector)

        try:
            return await async_retry_with_backoff(
                coro_func=fetch,
                max_retries=self.config.max_retries,
                base_delay=2.0,
                max_delay=60.0,
                retryable_exceptions=(AsyncBrightDataClientError,),
            )
        except AsyncBrightDataClientError as e:
            msg = f"Failed to fetch {url} after {self.config.max_retries} retries: {e}"
            raise RuntimeError(msg) from e

    async def _fetch_with_brightdata(self, url: str, wait_selector: str | None) -> str:
        """Make a single async request to Bright Data.

        Args:
            url: The URL to fetch.
            wait_selector: Optional CSS selector to wait for.

        Returns:
            The rendered HTML content.

        Raises:
            AsyncBrightDataClientError: If Bright Data returns an error.
        """
        logger.debug("Fetching URL via Bright Data (async): %s", url)
        start_time = time.time()

        try:
            async with async_playwright() as p:
                logger.debug("Connecting to Bright Data Scraping Browser (async)...")
                browser = await p.chromium.connect_over_cdp(self._browser_ws)

                try:
                    page = await browser.new_page()
                    await page.goto(
                        url,
                        timeout=self.DEFAULT_TIMEOUT,
                        wait_until="domcontentloaded",
                    )

                    if wait_selector:
                        try:
                            await page.wait_for_selector(
                                wait_selector,
                                timeout=self.WAIT_TIMEOUT,
                            )
                            logger.debug("Selector '%s' found", wait_selector)
                        except Exception as e:
                            logger.warning(
                                "Selector '%s' not found within timeout: %s",
                                wait_selector,
                                e,
                            )

                    html = await page.content()
                    duration = time.time() - start_time

                    # Record bandwidth
                    html_bytes = len(html.encode("utf-8"))
                    tracker = get_bandwidth_tracker()
                    stats = tracker.record_request(
                        url=url,
                        bytes_received=html_bytes,
                        duration_seconds=duration,
                    )

                    logger.debug(
                        "Fetched %d bytes in %.1fs (est. cost: $%.4f)",
                        html_bytes,
                        duration,
                        stats.estimated_cost,
                    )
                    return html

                finally:
                    await browser.close()

        except Exception as e:
            error_msg = str(e)
            is_connection = (
                "connect" in error_msg.lower() or "websocket" in error_msg.lower()
            )
            msg = f"Bright Data error for {url}: {error_msg}"
            logger.warning(msg)
            raise AsyncBrightDataClientError(
                msg,
                is_connection_error=is_connection,
            ) from e

    async def close(self) -> None:
        """No persistent resources to clean up."""
        pass


def create_async_client(config: ScrapingConfig) -> AsyncPageClient:
    """Create an async page client based on configuration.

    Args:
        config: Scraping configuration that determines client behavior.

    Returns:
        An AsyncPageClient instance.

    Raises:
        ValueError: If use_brightdata is False (async only supports Bright Data).
    """
    if config.use_brightdata:
        return AsyncBrightDataClient(config=config)
    raise ValueError("Async client requires use_brightdata=True")
