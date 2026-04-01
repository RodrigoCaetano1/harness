"""
Stats: manages iteration logging and dynamic sprint threshold computation.

Threshold rules:
- Sprints 1-4: fixed threshold from config.
- Sprint 5+: Q3 + 1.5×IQR of completed sprint iteration counts.
- Sprints with human_intervened entries contribute with weight 0.5 per iteration.

Also aggregates per-dimension scores for Meta-Harness signal.
"""

import json
import logging
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)


class Stats:
    """Tracks iteration results and computes dynamic sprint thresholds."""

    def __init__(self, log_path: Path, threshold_fixo: int = 50) -> None:
        self.log_path = log_path
        self.threshold_fixo = threshold_fixo
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    def log_iteration(
        self,
        sprint: int,
        iteration: int,
        scores: Dict[str, float],
        approved: bool,
        human_intervened: bool,
        browser_failures: int,
        project_type: str,
    ) -> None:
        """Append one iteration record to iteration_log.jsonl."""
        record = {
            "sprint": sprint,
            "iteration": iteration,
            "scores": scores,
            "approved": approved,
            "human_intervened": human_intervened,
            "browser_failures": browser_failures,
            "project_type": project_type,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        logger.debug("Logged iteration: sprint=%d iter=%d approved=%s", sprint, iteration, approved)

    def compute_threshold(self, sprint_num: int) -> int:
        """
        Return iteration threshold for sprint_num.
        Sprints 1-4: fixed threshold.
        Sprint 5+: Q3 + 1.5×IQR of weighted effective counts.
        Falls back to fixed threshold if insufficient history.
        """
        if sprint_num <= 4:
            logger.info("Threshold sprint %d (fixed): %d", sprint_num, self.threshold_fixo)
            return self.threshold_fixo

        counts = self._completed_sprint_effective_counts()
        if len(counts) < 4:
            logger.info(
                "Threshold sprint %d (fixed, insufficient history): %d",
                sprint_num, self.threshold_fixo,
            )
            return self.threshold_fixo

        try:
            import numpy as np
            arr = np.array(counts, dtype=float)
            q1, q3 = float(np.percentile(arr, 25)), float(np.percentile(arr, 75))
            iqr = q3 - q1
            dynamic = max(1, int(q3 + 1.5 * iqr))
            logger.info(
                "Threshold sprint %d (dynamic): Q3=%.1f IQR=%.1f → %d",
                sprint_num, q3, iqr, dynamic,
            )
            return dynamic
        except ImportError:
            logger.warning("numpy not available — using fixed threshold")
            return self.threshold_fixo

    def _completed_sprint_effective_counts(self) -> List[float]:
        """
        For each approved sprint, compute its effective iteration count.
        Iterations with human_intervened=true count as 0.5 each.
        """
        if not self.log_path.exists():
            return []

        records: List[dict] = []
        with self.log_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed log line")

        by_sprint: Dict[int, List[dict]] = defaultdict(list)
        for rec in records:
            by_sprint[rec["sprint"]].append(rec)

        counts = []
        for sprint_id, iters in by_sprint.items():
            if not any(r.get("approved") for r in iters):
                continue  # not a completed sprint
            effective = sum(
                0.5 if r.get("human_intervened") else 1.0
                for r in iters
            )
            counts.append(effective)

        return counts

    def get_dimension_summary(self) -> Dict[str, float]:
        """
        Return mean score per dimension across all logged iterations.
        Used by Meta-Harness to identify systematic Generator weaknesses.
        """
        if not self.log_path.exists():
            return {}

        dimension_scores: Dict[str, List[float]] = defaultdict(list)
        with self.log_path.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    for dim, score in rec.get("scores", {}).items():
                        dimension_scores[dim].append(float(score))
                except (json.JSONDecodeError, TypeError, ValueError):
                    pass

        return {
            dim: sum(vals) / len(vals)
            for dim, vals in dimension_scores.items()
            if vals
        }
