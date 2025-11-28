"""Bright Data billing and cost tracking utilities.

This module provides utilities to check account balance and track
costs of scraping operations using the Bright Data API.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import requests
from dotenv import load_dotenv

from idealista_scraper.utils.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Callable

logger = get_logger(__name__)

# Bright Data API endpoints
BRIGHTDATA_API_BASE = "https://api.brightdata.com"
BALANCE_ENDPOINT = f"{BRIGHTDATA_API_BASE}/customer/balance"
ZONE_ENDPOINT = f"{BRIGHTDATA_API_BASE}/zone"

# Billing update polling settings
BALANCE_POLL_INTERVAL_SECONDS = 5  # Check every 5 seconds
BALANCE_POLL_MAX_ATTEMPTS = 12  # Max 12 attempts = 60 seconds total

# Bright Data Scraping Browser pricing (per GB)
# https://brightdata.com/pricing/scraping-browser
SCRAPING_BROWSER_PRICE_PER_GB = 9.50  # USD per GB (average of tiers)

# Bytes per GB
BYTES_PER_GB = 1024 * 1024 * 1024


@dataclass
class RequestStats:
    """Statistics for a single request."""

    url: str
    bytes_received: int
    estimated_cost: float
    duration_seconds: float = 0.0


@dataclass
class BandwidthTracker:
    """Tracks bandwidth usage and estimates costs."""

    total_bytes: int = 0
    total_requests: int = 0
    price_per_gb: float = SCRAPING_BROWSER_PRICE_PER_GB
    requests: list[RequestStats] = field(default_factory=list)

    @property
    def total_gb(self) -> float:
        """Get total GB transferred."""
        return self.total_bytes / BYTES_PER_GB

    @property
    def total_cost(self) -> float:
        """Get total estimated cost."""
        return self.total_gb * self.price_per_gb

    @property
    def avg_bytes_per_request(self) -> float:
        """Get average bytes per request."""
        if self.total_requests == 0:
            return 0.0
        return self.total_bytes / self.total_requests

    @property
    def avg_cost_per_request(self) -> float:
        """Get average cost per request."""
        if self.total_requests == 0:
            return 0.0
        return self.total_cost / self.total_requests

    def record_request(
        self,
        url: str,
        bytes_received: int,
        duration_seconds: float = 0.0,
    ) -> RequestStats:
        """Record a request and its bandwidth usage."""
        estimated_cost = (bytes_received / BYTES_PER_GB) * self.price_per_gb
        stats = RequestStats(
            url=url,
            bytes_received=bytes_received,
            estimated_cost=estimated_cost,
            duration_seconds=duration_seconds,
        )
        self.requests.append(stats)
        self.total_bytes += bytes_received
        self.total_requests += 1
        return stats

    def __str__(self) -> str:
        """Return formatted summary."""
        return (
            f"Bandwidth: {self.total_bytes:,} bytes ({self.total_gb:.4f} GB) | "
            f"Requests: {self.total_requests} | "
            f"Est. cost: ${self.total_cost:.4f} "
            f"(avg ${self.avg_cost_per_request:.4f}/req)"
        )

    def summary(self) -> str:
        """Return detailed summary."""
        lines = [
            "Bandwidth Usage Summary:",
            f"   Total bytes:     {self.total_bytes:,} ({self.total_gb:.4f} GB)",
            f"   Total requests:  {self.total_requests}",
            f"   Avg per request: {self.avg_bytes_per_request:,.0f} bytes",
            f"   Price per GB:    ${self.price_per_gb:.2f}",
            f"   Est. total cost: ${self.total_cost:.4f}",
            f"   Est. cost/req:   ${self.avg_cost_per_request:.4f}",
        ]
        return "\n".join(lines)


_bandwidth_tracker: BandwidthTracker | None = None


def get_bandwidth_tracker() -> BandwidthTracker:
    """Get the global bandwidth tracker instance."""
    global _bandwidth_tracker
    if _bandwidth_tracker is None:
        _bandwidth_tracker = BandwidthTracker()
    return _bandwidth_tracker


def reset_bandwidth_tracker() -> BandwidthTracker:
    """Reset the global bandwidth tracker and return the old one."""
    global _bandwidth_tracker
    old_tracker = _bandwidth_tracker
    _bandwidth_tracker = BandwidthTracker()
    return old_tracker or BandwidthTracker()


@dataclass
class AccountBalance:
    """Bright Data account balance information."""

    balance: float
    pending_costs: float
    credit: float = 0.0
    prepayment: float = 0.0

    @property
    def available(self) -> float:
        """Get available balance (balance - pending costs)."""
        return self.balance - self.pending_costs

    def __str__(self) -> str:
        """Return formatted balance string."""
        return (
            f"Balance: ${self.balance:.2f} | "
            f"Pending costs: ${self.pending_costs:.2f} | "
            f"Available: ${self.available:.2f}"
        )


@dataclass
class CostReport:
    """Cost report for a scraping operation."""

    balance_before: float
    balance_after: float
    pending_before: float
    pending_after: float
    bandwidth_tracker: BandwidthTracker | None = None

    @property
    def balance_change(self) -> float:
        """Calculate balance change (negative = cost)."""
        return self.balance_after - self.balance_before

    @property
    def pending_change(self) -> float:
        """Calculate pending balance change."""
        return self.pending_after - self.pending_before

    @property
    def estimated_cost(self) -> float:
        """Estimate cost based on pending balance increase."""
        return max(0, self.pending_change)

    @property
    def bandwidth_cost(self) -> float:
        """Get cost estimated from bandwidth tracking."""
        if self.bandwidth_tracker:
            return self.bandwidth_tracker.total_cost
        return 0.0

    def __str__(self) -> str:
        """Return formatted cost report."""
        lines = [
            "Cost Report:",
            f"  Balance: ${self.balance_before:.2f} -> ${self.balance_after:.2f} "
            f"(change: ${self.balance_change:+.2f})",
            f"  Pending: ${self.pending_before:.2f} -> ${self.pending_after:.2f} "
            f"(change: ${self.pending_change:+.2f})",
            f"  API reported cost: ${self.estimated_cost:.4f}",
        ]
        if self.bandwidth_tracker:
            lines.append(
                f"  Bandwidth est. cost: ${self.bandwidth_cost:.4f} "
                f"({self.bandwidth_tracker.total_requests} requests, "
                f"{self.bandwidth_tracker.total_bytes:,} bytes)"
            )
        return "\n".join(lines)


def get_api_key() -> str:
    """Get Bright Data API key from environment."""
    load_dotenv()
    api_key = os.getenv("BRIGHTDATA_API_KEY")
    if not api_key:
        msg = (
            "BRIGHTDATA_API_KEY environment variable is required. "
            "Get your API key from https://brightdata.com/cp/setting/users"
        )
        raise ValueError(msg)
    return api_key


def get_balance() -> AccountBalance:
    """Get current Bright Data account balance."""
    api_key = get_api_key()
    try:
        response = requests.get(
            BALANCE_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return AccountBalance(
            balance=float(data.get("balance", 0)),
            pending_costs=float(data.get("pending_costs", 0)),
            credit=float(data.get("credit", 0)),
            prepayment=float(data.get("prepayment", 0)),
        )
    except requests.RequestException as e:
        msg = f"Failed to get balance from Bright Data API: {e}"
        raise RuntimeError(msg) from e


def get_zone_info(zone_name: str) -> dict[str, object]:
    """Get zone information from Bright Data API."""
    api_key = get_api_key()
    try:
        response = requests.get(
            ZONE_ENDPOINT,
            params={"zone": zone_name},
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=30,
        )
        response.raise_for_status()
        data: dict[str, object] = response.json()
        return data
    except requests.RequestException as e:
        msg = f"Failed to get zone info from Bright Data API: {e}"
        raise RuntimeError(msg) from e


class CostTracker:
    """Context manager for tracking costs of operations."""

    def __init__(self, use_bandwidth_tracking: bool = True) -> None:
        """Initialize the cost tracker."""
        self._balance_before: AccountBalance | None = None
        self._balance_after: AccountBalance | None = None
        self._report: CostReport | None = None
        self._use_bandwidth_tracking = use_bandwidth_tracking
        self._bandwidth_tracker: BandwidthTracker | None = None

    @property
    def report(self) -> CostReport | None:
        """Get the cost report after tracking completes."""
        return self._report

    def __enter__(self) -> CostTracker:
        """Record balance before operation."""
        try:
            self._balance_before = get_balance()
            logger.info("Balance before: %s", self._balance_before)
        except (ValueError, RuntimeError) as e:
            logger.warning("Could not get initial balance: %s", e)
            self._balance_before = None
        if self._use_bandwidth_tracking:
            reset_bandwidth_tracker()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: object,
    ) -> None:
        """Record balance after operation and calculate cost."""
        if self._use_bandwidth_tracking:
            self._bandwidth_tracker = reset_bandwidth_tracker()
            if self._bandwidth_tracker.total_requests > 0:
                logger.info("\n%s", self._bandwidth_tracker.summary())

        if self._balance_before is None:
            logger.warning("Cannot get API cost: initial balance unknown")
            if self._bandwidth_tracker and self._bandwidth_tracker.total_requests > 0:
                self._report = CostReport(
                    balance_before=0,
                    balance_after=0,
                    pending_before=0,
                    pending_after=0,
                    bandwidth_tracker=self._bandwidth_tracker,
                )
            return

        try:
            logger.info(
                "Waiting for Bright Data billing to update "
                "(polling every %ds, max %ds)...",
                BALANCE_POLL_INTERVAL_SECONDS,
                BALANCE_POLL_INTERVAL_SECONDS * BALANCE_POLL_MAX_ATTEMPTS,
            )
            self._balance_after = self._poll_for_balance_change()
            logger.info("Balance after: %s", self._balance_after)
            self._report = CostReport(
                balance_before=self._balance_before.balance,
                balance_after=self._balance_after.balance,
                pending_before=self._balance_before.pending_costs,
                pending_after=self._balance_after.pending_costs,
                bandwidth_tracker=self._bandwidth_tracker,
            )
            logger.info("\n%s", self._report)
        except (ValueError, RuntimeError) as e:
            logger.warning("Could not get final balance: %s", e)

    def _poll_for_balance_change(self) -> AccountBalance:
        """Poll the balance API until pending_costs changes or timeout."""
        initial_pending = (
            self._balance_before.pending_costs if self._balance_before else 0
        )
        for attempt in range(BALANCE_POLL_MAX_ATTEMPTS):
            time.sleep(BALANCE_POLL_INTERVAL_SECONDS)
            current = get_balance()
            if current.pending_costs != initial_pending:
                logger.debug(
                    "Balance updated after %d seconds",
                    (attempt + 1) * BALANCE_POLL_INTERVAL_SECONDS,
                )
                return current
            logger.debug(
                "Attempt %d/%d: pending still $%.2f",
                attempt + 1,
                BALANCE_POLL_MAX_ATTEMPTS,
                current.pending_costs,
            )
        logger.warning(
            "Balance did not update within %d seconds. "
            "Cost may not be accurately reported.",
            BALANCE_POLL_INTERVAL_SECONDS * BALANCE_POLL_MAX_ATTEMPTS,
        )
        return get_balance()


def track_cost[T](func: Callable[[], T]) -> tuple[T, CostReport | None]:
    """Run a function and track its cost."""
    with CostTracker() as tracker:
        result = func()
    return result, tracker.report
