"""Time and retry utilities for the Idealista scraper."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from idealista_scraper.utils.logging import get_logger

logger = get_logger(__name__)


def sleep_with_jitter(base_delay: float, jitter_factor: float = 0.1) -> None:
    """Sleep for a base delay with random jitter.

    Args:
        base_delay: The base delay in seconds.
        jitter_factor: The factor of randomness to add (0.0 to 1.0).
            Default is 0.1 (10% jitter).
    """
    jitter = random.uniform(-jitter_factor, jitter_factor) * base_delay
    actual_delay = max(0, base_delay + jitter)
    time.sleep(actual_delay)


def retry_with_backoff[T](
    func: Callable[[], T],
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    exponential_base: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> T:
    """Retry a function with exponential backoff.

    Args:
        func: The function to call (no arguments).
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay between retries in seconds.
        max_delay: Maximum delay between retries in seconds.
        exponential_base: Base for exponential backoff calculation.
        retryable_exceptions: Tuple of exception types that should trigger a retry.

    Returns:
        The return value of the function if successful.

    Raises:
        Exception: Re-raises the last exception if all retries fail.
    """
    last_exception: Exception | None = None

    for attempt in range(max_retries + 1):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
            if attempt == max_retries:
                logger.error(
                    "All %d retry attempts failed. Last error: %s",
                    max_retries + 1,
                    e,
                )
                raise

            delay = min(base_delay * (exponential_base**attempt), max_delay)
            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.1f seconds...",
                attempt + 1,
                max_retries + 1,
                e,
                delay,
            )
            sleep_with_jitter(delay)

    # This should never be reached, but satisfies type checker
    if last_exception:
        raise last_exception
    raise RuntimeError("Unexpected state in retry_with_backoff")
