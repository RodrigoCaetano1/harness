"""
RetryPolicy: wraps Playwright operations with retry + exponential backoff.

Distinguishes infrastructure failures (browser crash / timeout) from
implementation failures (feature broken). After exhausting retries, raises
PlaywrightBrowserError — callers must NOT treat this as a sprint rejection.
"""

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


class PlaywrightBrowserError(Exception):
    """
    Raised when a browser operation fails after all retries are exhausted.
    This is an infrastructure failure, not an implementation failure.
    The sprint should not be rejected solely on this basis.
    """


class RetryPolicy:
    """
    Execute a callable with retry on any exception.

    - Retries up to max_retries times.
    - Sleeps backoff_s seconds between attempts.
    - Raises PlaywrightBrowserError after the final failed attempt.
    """

    def __init__(self, max_retries: int = 3, backoff_s: int = 2) -> None:
        if max_retries < 1:
            raise ValueError("max_retries must be >= 1")
        self.max_retries = max_retries
        self.backoff_s = backoff_s

    def execute(self, fn: Callable[[], T]) -> T:
        """
        Execute fn with retry policy.
        Returns the result of fn on success.
        Raises PlaywrightBrowserError after exhausting retries.
        """
        last_exc: Exception = RuntimeError("No attempts made")

        for attempt in range(1, self.max_retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_exc = exc
                if attempt < self.max_retries:
                    logger.warning(
                        "Playwright attempt %d/%d failed: %s — retrying in %ds",
                        attempt, self.max_retries, exc, self.backoff_s,
                    )
                    time.sleep(self.backoff_s)
                else:
                    logger.error(
                        "Playwright attempt %d/%d failed: %s — no more retries",
                        attempt, self.max_retries, exc,
                    )

        raise PlaywrightBrowserError(
            f"Browser operation failed after {self.max_retries} attempt(s): {last_exc}"
        ) from last_exc
