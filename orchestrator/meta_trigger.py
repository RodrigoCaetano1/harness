"""
MetaTrigger: monitors post-execution counters and fires the Meta-Harness
when either completed-executions or human-review thresholds are reached.

Counters are tracked globally and per project_type.
State is persisted in artifacts/meta_trigger_state.json.
"""

import json
import logging
from pathlib import Path
from typing import Optional

from config import Config

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")
STATE_PATH = ARTIFACTS_DIR / "meta_trigger_state.json"


class MetaTrigger:
    """
    Tracks completed executions and human reviews per project_type and globally.
    Triggers the Meta-Harness optimization loop when thresholds are reached.
    """

    def __init__(self, config: Config) -> None:
        self.config = config
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if STATE_PATH.exists():
            try:
                return json.loads(STATE_PATH.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning(
                    "Could not load meta_trigger_state.json (%s) — starting fresh", exc
                )
        return {
            "global": {"executions": 0, "reviews": 0},
            "by_project_type": {},
        }

    def _save_state(self) -> None:
        STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        STATE_PATH.write_text(
            json.dumps(self._state, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def _pt_counters(self, project_type: str) -> dict:
        return self._state["by_project_type"].setdefault(
            project_type, {"executions": 0, "reviews": 0}
        )

    def record_execution(self, project_type: str) -> None:
        """Increment execution counter (global + project_type)."""
        self._state["global"]["executions"] += 1
        self._pt_counters(project_type)["executions"] += 1
        self._save_state()
        logger.info(
            "MetaTrigger: execution recorded — global=%d type=%s/%d",
            self._state["global"]["executions"],
            project_type,
            self._pt_counters(project_type)["executions"],
        )

    def record_review(self, project_type: str) -> None:
        """Increment human-review counter (global + project_type)."""
        self._state["global"]["reviews"] += 1
        self._pt_counters(project_type)["reviews"] += 1
        self._save_state()
        logger.info(
            "MetaTrigger: review recorded — global=%d type=%s/%d",
            self._state["global"]["reviews"],
            project_type,
            self._pt_counters(project_type)["reviews"],
        )

    def should_trigger(self, project_type: Optional[str] = None) -> bool:
        """
        Check if Meta-Harness should run (OR of global and per-type thresholds).
        """
        g = self._state["global"]
        if (
            g["executions"] >= self.config.threshold_execucoes_meta
            or g["reviews"] >= self.config.threshold_reviews_meta
        ):
            logger.info("MetaTrigger: global threshold reached")
            return True

        if project_type:
            pt = self._state["by_project_type"].get(project_type, {})
            if (
                pt.get("executions", 0) >= self.config.threshold_execucoes_meta
                or pt.get("reviews", 0) >= self.config.threshold_reviews_meta
            ):
                logger.info(
                    "MetaTrigger: project_type '%s' threshold reached", project_type
                )
                return True

        return False

    def reset_counters(self, project_type: Optional[str] = None) -> None:
        """Reset counters after a Meta-Harness run."""
        self._state["global"] = {"executions": 0, "reviews": 0}
        if project_type and project_type in self._state["by_project_type"]:
            self._state["by_project_type"][project_type] = {
                "executions": 0,
                "reviews": 0,
            }
        self._save_state()
        logger.info("MetaTrigger: counters reset (project_type=%s)", project_type)

    def run_meta_harness(self, project_type: str) -> None:
        """
        Entry point for the offline Meta-Harness optimization loop.

        In production, this should launch an external process or script that:
        - Reads iteration_log.jsonl for per-dimension score signals
        - Identifies systematic Generator weaknesses
        - Optimizes prompts via DSPy or similar
        - Writes updated prompts to prompts/

        Replace this stub with a subprocess.run() call or similar.
        """
        logger.info(
            "META-HARNESS TRIGGERED — project_type='%s'. "
            "Implement the external optimization loop in this method.",
            project_type,
        )
        self.reset_counters(project_type)
