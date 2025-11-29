"""Tests for async time utilities."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from idealista_scraper.utils.async_time_utils import (
    async_retry_with_backoff,
    async_sleep_with_jitter,
)


class TestAsyncSleepWithJitter:
    """Tests for async_sleep_with_jitter function."""

    @pytest.mark.asyncio
    async def test_sleep_with_no_jitter(self) -> None:
        """Test sleep with zero jitter factor."""
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            await async_sleep_with_jitter(1.0, jitter_factor=0.0)
            mock_sleep.assert_called_once_with(1.0)

    @pytest.mark.asyncio
    async def test_sleep_with_jitter_in_range(self) -> None:
        """Test that sleep delay stays within jitter range."""
        calls: list[float] = []

        async def capture_sleep(delay: float) -> None:
            calls.append(delay)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            # Run multiple times to test randomness
            for _ in range(100):
                await async_sleep_with_jitter(10.0, jitter_factor=0.1)

        # All delays should be within 10% of base (9.0 to 11.0)
        for delay in calls:
            assert 9.0 <= delay <= 11.0, f"Delay {delay} outside expected range"

    @pytest.mark.asyncio
    async def test_sleep_with_large_jitter(self) -> None:
        """Test sleep with large jitter factor."""
        calls: list[float] = []

        async def capture_sleep(delay: float) -> None:
            calls.append(delay)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            for _ in range(100):
                await async_sleep_with_jitter(10.0, jitter_factor=0.5)

        # All delays should be within 50% of base (5.0 to 15.0)
        for delay in calls:
            assert 5.0 <= delay <= 15.0, f"Delay {delay} outside expected range"

    @pytest.mark.asyncio
    async def test_sleep_never_negative(self) -> None:
        """Test that sleep delay is never negative."""
        calls: list[float] = []

        async def capture_sleep(delay: float) -> None:
            calls.append(delay)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            # With jitter_factor=1.0, delay could theoretically be 0 or negative
            for _ in range(100):
                await async_sleep_with_jitter(0.5, jitter_factor=1.0)

        # All delays should be >= 0
        for delay in calls:
            assert delay >= 0, f"Delay {delay} should not be negative"

    @pytest.mark.asyncio
    async def test_sleep_default_jitter_factor(self) -> None:
        """Test default jitter factor is 0.1 (10%)."""
        calls: list[float] = []

        async def capture_sleep(delay: float) -> None:
            calls.append(delay)

        with patch("asyncio.sleep", side_effect=capture_sleep):
            for _ in range(100):
                await async_sleep_with_jitter(10.0)  # No jitter_factor specified

        # Default jitter is 0.1, so delays should be 9.0 to 11.0
        for delay in calls:
            assert 9.0 <= delay <= 11.0, f"Delay {delay} outside expected range"


class TestAsyncRetryWithBackoff:
    """Tests for async_retry_with_backoff function."""

    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self) -> None:
        """Test that successful coroutine is not retried."""
        call_count = 0

        async def successful_coro() -> str:
            nonlocal call_count
            call_count += 1
            return "success"

        result = await async_retry_with_backoff(successful_coro)
        assert result == "success"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure_then_success(self) -> None:
        """Test retry when coroutine fails then succeeds."""
        call_count = 0

        async def fail_then_succeed() -> str:
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success after retries"

        with patch(
            "idealista_scraper.utils.async_time_utils.async_sleep_with_jitter",
            new_callable=AsyncMock,
        ):
            result = await async_retry_with_backoff(
                fail_then_succeed,
                max_retries=5,
                retryable_exceptions=(ValueError,),
            )

        assert result == "success after retries"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_raises_after_max_retries(self) -> None:
        """Test that exception is raised after max retries exhausted."""
        call_count = 0

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Permanent failure")

        with (
            patch(
                "idealista_scraper.utils.async_time_utils.async_sleep_with_jitter",
                new_callable=AsyncMock,
            ),
            pytest.raises(ValueError, match="Permanent failure"),
        ):
            await async_retry_with_backoff(
                always_fails,
                max_retries=3,
                retryable_exceptions=(ValueError,),
            )

        # Should have tried 4 times (initial + 3 retries)
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_non_retryable_exception_not_retried(self) -> None:
        """Test that non-retryable exceptions are raised immediately."""
        call_count = 0

        async def raises_type_error() -> str:
            nonlocal call_count
            call_count += 1
            raise TypeError("Not retryable")

        with pytest.raises(TypeError, match="Not retryable"):
            await async_retry_with_backoff(
                raises_type_error,
                max_retries=5,
                retryable_exceptions=(ValueError,),  # Only ValueError is retryable
            )

        # Should have only tried once
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_exponential_backoff_delay(self) -> None:
        """Test that delay increases exponentially."""
        call_count = 0
        delays: list[float] = []

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Failure")

        async def capture_delay(delay: float, **_kwargs: float) -> None:
            delays.append(delay)

        with (
            patch(
                "idealista_scraper.utils.async_time_utils.async_sleep_with_jitter",
                side_effect=capture_delay,
            ),
            pytest.raises(ValueError),
        ):
            await async_retry_with_backoff(
                always_fails,
                max_retries=3,
                base_delay=1.0,
                exponential_base=2.0,
                retryable_exceptions=(ValueError,),
            )

        # Delays should be: 1.0, 2.0, 4.0 (exponential)
        assert delays == [1.0, 2.0, 4.0]

    @pytest.mark.asyncio
    async def test_max_delay_respected(self) -> None:
        """Test that delay does not exceed max_delay."""
        delays: list[float] = []

        async def always_fails() -> str:
            raise ValueError("Failure")

        async def capture_delay(delay: float, **_kwargs: float) -> None:
            delays.append(delay)

        with (
            patch(
                "idealista_scraper.utils.async_time_utils.async_sleep_with_jitter",
                side_effect=capture_delay,
            ),
            pytest.raises(ValueError),
        ):
            await async_retry_with_backoff(
                always_fails,
                max_retries=5,
                base_delay=10.0,
                max_delay=30.0,
                exponential_base=2.0,
                retryable_exceptions=(ValueError,),
            )

        # Delays: 10, 20, 30 (capped), 30 (capped), 30 (capped)
        assert delays == [10.0, 20.0, 30.0, 30.0, 30.0]

    @pytest.mark.asyncio
    async def test_default_max_retries(self) -> None:
        """Test default max_retries is 3."""
        call_count = 0

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise RuntimeError("Failure")

        with (
            patch(
                "idealista_scraper.utils.async_time_utils.async_sleep_with_jitter",
                new_callable=AsyncMock,
            ),
            pytest.raises(RuntimeError),
        ):
            await async_retry_with_backoff(always_fails)

        # Default is 3 retries, so 4 total attempts
        assert call_count == 4

    @pytest.mark.asyncio
    async def test_returns_correct_type(self) -> None:
        """Test that return type is preserved."""

        async def returns_int() -> int:
            return 42

        async def returns_dict() -> dict[str, int]:
            return {"a": 1, "b": 2}

        int_result = await async_retry_with_backoff(returns_int)
        assert int_result == 42
        assert isinstance(int_result, int)

        dict_result = await async_retry_with_backoff(returns_dict)
        assert dict_result == {"a": 1, "b": 2}
        assert isinstance(dict_result, dict)

    @pytest.mark.asyncio
    async def test_zero_max_retries(self) -> None:
        """Test with max_retries=0 (no retries)."""
        call_count = 0

        async def always_fails() -> str:
            nonlocal call_count
            call_count += 1
            raise ValueError("Failure")

        with pytest.raises(ValueError):
            await async_retry_with_backoff(
                always_fails,
                max_retries=0,
                retryable_exceptions=(ValueError,),
            )

        # Only one attempt with no retries
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_multiple_exception_types(self) -> None:
        """Test retrying on multiple exception types."""
        call_count = 0

        async def raises_different_exceptions() -> str:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ValueError("First error")
            elif call_count == 2:
                raise ConnectionError("Second error")
            return "success"

        with patch(
            "idealista_scraper.utils.async_time_utils.async_sleep_with_jitter",
            new_callable=AsyncMock,
        ):
            result = await async_retry_with_backoff(
                raises_different_exceptions,
                max_retries=3,
                retryable_exceptions=(ValueError, ConnectionError),
            )

        assert result == "success"
        assert call_count == 3
