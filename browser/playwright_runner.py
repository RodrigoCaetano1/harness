"""
PlaywrightRunner: executes browser-based test criteria via Playwright.

Each criterion is a dict with:
  - url (str): page to navigate to
  - selector (str | None): CSS selector to locate
  - expected_text (str | None): text that must appear in the element
  - expected_state (str | None): 'visible' | 'hidden' | 'enabled' | 'disabled'
  - action (str): human-readable description (for logging only)

Returns True if criterion passes, False if it fails.
Raises PlaywrightBrowserError on repeated browser crashes (via RetryPolicy).
"""

import logging
from typing import Any, Dict, Optional

from browser.retry_policy import PlaywrightBrowserError, RetryPolicy

logger = logging.getLogger(__name__)

DEFAULT_URL = "http://localhost:5173"
NAV_TIMEOUT_MS = 15_000
SELECTOR_TIMEOUT_MS = 10_000


class PlaywrightRunner:
    """Runs individual Playwright test criteria with retry support."""

    def __init__(self, retry_policy: RetryPolicy) -> None:
        self.retry_policy = retry_policy

    def run_criterion(self, criterion: Dict[str, Any]) -> bool:
        """
        Execute a single criterion.
        Returns True on pass, False on failure.
        Raises PlaywrightBrowserError on infrastructure failure.
        """
        action = criterion.get("action", "(no action description)")
        logger.info("Testing criterion: %s", action)

        def _attempt() -> bool:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                try:
                    page = browser.new_page()
                    url = criterion.get("url") or DEFAULT_URL
                    page.goto(url, timeout=NAV_TIMEOUT_MS)

                    selector: Optional[str] = criterion.get("selector")
                    expected_text: Optional[str] = criterion.get("expected_text")
                    expected_state: Optional[str] = criterion.get("expected_state")

                    if not selector:
                        # No selector — just check navigation succeeded
                        logger.debug("Criterion has no selector — checking page load only")
                        return True

                    # Wait for element
                    locator = page.locator(selector)

                    if expected_state == "hidden":
                        locator.wait_for(state="hidden", timeout=SELECTOR_TIMEOUT_MS)
                        return True

                    locator.wait_for(state="visible", timeout=SELECTOR_TIMEOUT_MS)

                    if expected_state in ("enabled", "disabled"):
                        is_enabled = locator.is_enabled()
                        if expected_state == "enabled":
                            return is_enabled
                        return not is_enabled

                    if expected_text:
                        actual_text = locator.inner_text()
                        match = expected_text in actual_text
                        if not match:
                            logger.debug(
                                "Text mismatch: expected '%s' in '%s'",
                                expected_text, actual_text[:200],
                            )
                        return match

                    # Element found and visible — criterion passes
                    return True

                finally:
                    browser.close()

        try:
            result = self.retry_policy.execute(_attempt)
            logger.info("Criterion '%s': %s", action, "PASS" if result else "FAIL")
            return result
        except PlaywrightBrowserError:
            logger.error("Browser failure on criterion '%s'", action)
            raise
