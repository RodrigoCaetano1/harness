"""
Rollback: smoke-tests approved features and performs git rollbacks on regression.

Two functions:
1. smoke_test() — run at the start of each sprint (except sprint 1).
   Tests the smoke_criteria of all features with passes: true.
   Returns True if regression detected.

2. rollback_to_last_commit() — automatic rollback on regression.
3. rollback_manual(commit_hash) — manual rollback triggered via human_review.
"""

import json
import logging
import subprocess
from pathlib import Path

from browser.playwright_runner import PlaywrightRunner
from browser.retry_policy import RetryPolicy

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")


class Rollback:
    """Smoke-tests passing features and rolls back the repo on regression."""

    def __init__(self) -> None:
        self._runner = PlaywrightRunner(RetryPolicy())

    def smoke_test(self) -> bool:
        """
        Run smoke_criteria for all features with passes: true.
        Returns True if any criterion fails (regression detected).
        Returns False if all pass or no passed features exist.
        """
        feature_list_path = ARTIFACTS_DIR / "feature_list.json"
        if not feature_list_path.exists():
            logger.warning("feature_list.json not found — skipping smoke test")
            return False

        try:
            features = json.loads(
                feature_list_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Could not load feature_list.json for smoke test: %s", exc)
            return False

        passed_features = [f for f in features if f.get("passes") is True]
        if not passed_features:
            logger.info("Smoke test: no passed features — skipping")
            return False

        logger.info(
            "Smoke test: %d passed feature(s) to check", len(passed_features)
        )
        for feature in passed_features:
            feature_id = feature.get("id", "?")
            criteria = feature.get("smoke_criteria", [])
            if not criteria:
                logger.debug(
                    "Feature %s has no smoke_criteria — skipping", feature_id
                )
                continue
            for criterion in criteria:
                try:
                    passed = self._runner.run_criterion(criterion)
                    if not passed:
                        logger.error(
                            "Smoke FAIL: feature '%s' criterion '%s'",
                            feature_id, criterion.get("action", ""),
                        )
                        return True
                except Exception as exc:
                    logger.error(
                        "Smoke test exception on feature '%s': %s", feature_id, exc
                    )
                    return True

        logger.info("Smoke test: all criteria passed")
        return False

    def rollback_to_last_commit(self) -> None:
        """Hard-reset working tree and index to HEAD."""
        result = subprocess.run(
            ["git", "reset", "--hard", "HEAD"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git reset --hard HEAD failed:\n{result.stderr}"
            )
        logger.info("Rolled back to HEAD")

    def rollback_manual(self, commit_hash: str) -> None:
        """
        Roll back to a specific commit hash.
        Triggered by human_review when operator chooses to revert.
        """
        if not commit_hash or len(commit_hash) < 7:
            raise ValueError(f"Invalid commit hash: '{commit_hash}'")
        result = subprocess.run(
            ["git", "reset", "--hard", commit_hash],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"git reset --hard {commit_hash} failed:\n{result.stderr}"
            )
        logger.info("Rolled back to %s", commit_hash)
