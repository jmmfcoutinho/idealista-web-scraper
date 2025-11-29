"""Tests for async client functionality.

Tests the AsyncBrightDataClient and related async client utilities
using mocks to avoid actual network requests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from idealista_scraper.config import ScrapingConfig
from idealista_scraper.scraping.async_client import (
    AsyncBrightDataClient,
    AsyncBrightDataClientError,
    create_async_client,
)


class TestAsyncBrightDataClientError:
    """Tests for AsyncBrightDataClientError exception."""

    def test_error_with_message(self) -> None:
        """Test creating error with message."""
        error = AsyncBrightDataClientError("Connection failed")
        assert str(error) == "Connection failed"
        assert error.is_connection_error is False

    def test_error_with_connection_flag(self) -> None:
        """Test creating error with connection flag."""
        error = AsyncBrightDataClientError(
            "WebSocket connection failed",
            is_connection_error=True,
        )
        assert str(error) == "WebSocket connection failed"
        assert error.is_connection_error is True


class TestAsyncBrightDataClient:
    """Tests for AsyncBrightDataClient."""

    def test_init_with_credentials(self) -> None:
        """Test initialization with explicit credentials."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
        )
        assert client.browser_user == "test-user"
        assert client.browser_pass == "test-pass"
        assert client._request_count == 0

    def test_init_with_config(self) -> None:
        """Test initialization with ScrapingConfig."""
        config = ScrapingConfig(delay_seconds=3.0, max_retries=5)
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=config,
        )
        assert client.config.delay_seconds == 3.0
        assert client.config.max_retries == 5

    def test_browser_ws_url_format(self) -> None:
        """Test WebSocket URL is properly formatted."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
        )
        expected = "wss://test-user:test-pass@brd.superproxy.io:9222"
        assert client._browser_ws == expected

    @pytest.mark.asyncio
    async def test_close_is_noop(self) -> None:
        """Test that close() doesn't raise errors."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
        )
        # Should complete without error
        await client.close()

    @pytest.mark.asyncio
    async def test_get_html_success(self) -> None:
        """Test successful HTML fetch with mocked playwright."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=0, max_retries=1),
        )

        # Mock the entire async_playwright context
        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>Test content</html>")

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "idealista_scraper.scraping.async_client.async_playwright",
            return_value=mock_async_playwright,
        ):
            result = await client.get_html(
                "https://www.example.com",
                wait_selector="article.item",
            )

        assert result == "<html>Test content</html>"
        mock_chromium.connect_over_cdp.assert_called_once()
        mock_page.goto.assert_called_once()
        mock_page.wait_for_selector.assert_called_once_with(
            "article.item",
            timeout=client.WAIT_TIMEOUT,
        )

    @pytest.mark.asyncio
    async def test_get_html_without_wait_selector(self) -> None:
        """Test fetch without wait_selector."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=0, max_retries=1),
        )

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.wait_for_selector = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>No selector</html>")

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "idealista_scraper.scraping.async_client.async_playwright",
            return_value=mock_async_playwright,
        ):
            result = await client.get_html("https://www.example.com")

        assert result == "<html>No selector</html>"
        # wait_for_selector should not be called
        mock_page.wait_for_selector.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_html_retry_on_error(self) -> None:
        """Test retry behavior on transient errors."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=0, max_retries=2),
        )

        call_count = 0

        async def mock_connect(*args, **kwargs):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise Exception("Connection failed")
            # Return successful browser on second attempt
            mock_page = AsyncMock()
            mock_page.goto = AsyncMock()
            mock_page.content = AsyncMock(return_value="<html>Success</html>")

            mock_browser = AsyncMock()
            mock_browser.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            return mock_browser

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = mock_connect

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "idealista_scraper.scraping.async_client.async_playwright",
                return_value=mock_async_playwright,
            ),
            patch(
                "idealista_scraper.scraping.async_client.async_sleep_with_jitter",
                new=AsyncMock(),
            ),
        ):
            result = await client.get_html("https://www.example.com")

        assert result == "<html>Success</html>"
        assert call_count == 2

    @pytest.mark.asyncio
    async def test_get_html_raises_after_max_retries(self) -> None:
        """Test that RuntimeError is raised after max retries."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=0, max_retries=2),
        )

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = AsyncMock(
            side_effect=Exception("Connection failed")
        )

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "idealista_scraper.scraping.async_client.async_playwright",
                return_value=mock_async_playwright,
            ),
            patch(
                "idealista_scraper.scraping.async_client.async_sleep_with_jitter",
                new=AsyncMock(),
            ),
            pytest.raises(RuntimeError, match="Failed to fetch"),
        ):
            await client.get_html("https://www.example.com")

    @pytest.mark.asyncio
    async def test_request_count_increments(self) -> None:
        """Test that request count increments with each request."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=0, max_retries=1),
        )

        assert client._request_count == 0

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>Test</html>")

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "idealista_scraper.scraping.async_client.async_playwright",
            return_value=mock_async_playwright,
        ):
            await client.get_html("https://www.example.com")
            assert client._request_count == 1

            await client.get_html("https://www.example.com/page2")
            assert client._request_count == 2


class TestAsyncBrightDataClientDelays:
    """Tests for delay behavior in AsyncBrightDataClient."""

    @pytest.mark.asyncio
    async def test_no_delay_on_first_request(self) -> None:
        """Test that first request doesn't have delay."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=5.0, max_retries=1),
        )

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>Test</html>")

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "idealista_scraper.scraping.async_client.async_playwright",
                return_value=mock_async_playwright,
            ),
            patch(
                "idealista_scraper.scraping.async_client.async_sleep_with_jitter",
            ) as mock_sleep,
        ):
            await client.get_html("https://www.example.com")
            # First request should not call sleep
            mock_sleep.assert_not_called()

    @pytest.mark.asyncio
    async def test_delay_on_subsequent_requests(self) -> None:
        """Test that subsequent requests have delay."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=5.0, max_retries=1),
        )

        # Simulate that we already made a request
        client._request_count = 1

        mock_page = AsyncMock()
        mock_page.goto = AsyncMock()
        mock_page.content = AsyncMock(return_value="<html>Test</html>")

        mock_browser = AsyncMock()
        mock_browser.new_page = AsyncMock(return_value=mock_page)
        mock_browser.close = AsyncMock()

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = AsyncMock(return_value=mock_browser)

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with (
            patch(
                "idealista_scraper.scraping.async_client.async_playwright",
                return_value=mock_async_playwright,
            ),
            patch(
                "idealista_scraper.scraping.async_client.async_sleep_with_jitter",
            ) as mock_sleep,
        ):
            mock_sleep.return_value = None
            await client.get_html("https://www.example.com")
            # Should call sleep with configured delay
            mock_sleep.assert_called_once_with(5.0)


class TestCreateAsyncClient:
    """Tests for create_async_client factory function."""

    def test_create_with_brightdata_enabled(self) -> None:
        """Test creating client with use_brightdata=True."""
        config = ScrapingConfig(use_brightdata=True)

        with patch.dict(
            "os.environ",
            {
                "BRIGHTDATA_BROWSER_USER": "test-user",
                "BRIGHTDATA_BROWSER_PASS": "test-pass",
            },
        ):
            client = create_async_client(config)
            assert isinstance(client, AsyncBrightDataClient)

    def test_create_with_brightdata_disabled(self) -> None:
        """Test that ValueError is raised when use_brightdata=False."""
        config = ScrapingConfig(use_brightdata=False)

        with pytest.raises(ValueError, match="requires use_brightdata=True"):
            create_async_client(config)


class TestAsyncClientConcurrency:
    """Tests for concurrent usage of async client."""

    @pytest.mark.asyncio
    async def test_concurrent_requests(self) -> None:
        """Test that multiple concurrent requests can be made."""
        client = AsyncBrightDataClient(
            browser_user="test-user",
            browser_pass="test-pass",
            config=ScrapingConfig(delay_seconds=0, max_retries=1),
        )

        call_count = 0

        async def mock_connect(*args, **kwargs):  # noqa: ARG001
            nonlocal call_count
            call_count += 1
            # Simulate some async work
            await asyncio.sleep(0.01)

            mock_page = AsyncMock()
            mock_page.goto = AsyncMock()
            mock_page.content = AsyncMock(
                return_value=f"<html>Response {call_count}</html>"
            )

            mock_browser = AsyncMock()
            mock_browser.new_page = AsyncMock(return_value=mock_page)
            mock_browser.close = AsyncMock()
            return mock_browser

        mock_chromium = AsyncMock()
        mock_chromium.connect_over_cdp = mock_connect

        mock_playwright = MagicMock()
        mock_playwright.chromium = mock_chromium

        mock_async_playwright = AsyncMock()
        mock_async_playwright.__aenter__ = AsyncMock(return_value=mock_playwright)
        mock_async_playwright.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "idealista_scraper.scraping.async_client.async_playwright",
            return_value=mock_async_playwright,
        ):
            # Make 3 concurrent requests
            results = await asyncio.gather(
                client.get_html("https://www.example.com/1"),
                client.get_html("https://www.example.com/2"),
                client.get_html("https://www.example.com/3"),
            )

        assert len(results) == 3
        assert call_count == 3
        # All results should contain HTML
        for result in results:
            assert "<html>" in result
