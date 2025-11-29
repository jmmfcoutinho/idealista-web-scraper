"""Async time and retry utilities for the Idealista scraper."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable

from idealista_scraper.utils.logging import get_logger

logger = get_logger(__name__)


async def async_sleep_with_jitter(
    base_delay: float,
    jitter_factor: float = 0.1,
) -> None:
    """Async sleep with random jitter for anti-detection.

    Args:
        base_delay: The base delay in seconds.
        jitter_factor: The factor of randomness to add (0.0 to 1.0).
            Default is 0.1 (10% jitter).
    """
    jitter = random.uniform(-jitter_factor, jitter_factor) * base_delay
    actual_delay = max(0, base_delay + jitter)
    await asyncio.sleep(actual_delay)


async def async_retry_with_backoff[T](
    coro_func: Callable[[], Awaitable[T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry an async function with exponential backoff.

    Args:
        coro_func: A zero-argument async function to call.
        max_retries: Maximum retry attempts.
        base_delay: Initial delay between retries.
        max_delay: Maximum delay between retries.
        exponential_base: Base for exponential backoff.
        retryable_exceptions: Exception types that trigger retry.

    Returns:
        The return value of the coroutine.

    Raises:
        The last exception if all retries fail.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return await coro_func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt == max_retries:
                logger.error(
                    "All %d attempts failed. Last error: %s",
                    max_retries + 1,
                    e,
                )
                raise

            delay = min(base_delay * (exponential_base**attempt), max_delay)
            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt + 1,
                max_retries + 1,
                e,
                delay,
            )
            await async_sleep_with_jitter(delay)

    # This should never be reached, but satisfies type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected state in async_retry_with_backoff")
