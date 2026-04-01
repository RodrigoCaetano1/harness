"""
SprintLoop: orchestrates the full lifecycle of one sprint.

Sequence per sprint:
1. Smoke test (skip on sprint 1)
2. Contract negotiation
3. Implementation + evaluation loop (via IterationTracker)
4. On approval: mark feature passed, git commit, update progress.md

Feature-list integrity is enforced on every write.
"""

import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from agents.evaluator import EvaluatorAgent
from agents.generator import GeneratorAgent
from config import Config
from orchestrator.human_review import HumanReview
from orchestrator.iteration_tracker import IterationTracker
from orchestrator.negotiation import Negotiation
from orchestrator.rollback import Rollback
from orchestrator.stats import Stats

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")
REQUIRED_FEATURE_FIELDS = {"id", "name", "category", "description", "user_story", "smoke_criteria", "passes"}


class SprintLoop:
    """Manages one sprint end-to-end."""

    def __init__(self, config: Config, project_type: str = "default") -> None:
        self.config = config
        self.project_type = project_type
        self.generator = GeneratorAgent(config)
        self.evaluator = EvaluatorAgent(config)
        self.rollback = Rollback()
        self.stats = Stats(
            ARTIFACTS_DIR / "iteration_log.jsonl",
            threshold_fixo=config.threshold_fixo_iteracoes,
        )
        self.human_review = HumanReview()

    def run(self, sprint_num: int) -> bool:
        """
        Execute a full sprint.
        Returns True if approved, False if aborted or failed without recovery.
        """
        logger.info("=== Sprint %02d starting ===", sprint_num)

        # Step 1: smoke test (skip sprint 1 — nothing has passed yet)
        if sprint_num > 1:
            regression = self.rollback.smoke_test()
            if regression:
                logger.warning("Regression detected on sprint %02d — rolling back", sprint_num)
                self.rollback.rollback_to_last_commit()

        # Step 2: contract negotiation
        negotiation = Negotiation(self.config, sprint_num)
        contract_approved = negotiation.run()

        if not contract_approved:
            logger.warning("Negotiation deadlock on sprint %02d", sprint_num)
            decision = self.human_review.prompt(
                sprint=sprint_num,
                iteration=0,
                reason="Contract negotiation deadlock",
                last_feedbacks=[],
            )
            if decision == "abort":
                return False
            # 'continue' or 'rewrite_contract' — proceed with whatever contract is current

        # Step 3: implementation + evaluation loop
        tracker = IterationTracker(sprint_num, self.config, self.stats)
        return tracker.run(
            generator=self.generator,
            evaluator=self.evaluator,
            human_review=self.human_review,
            project_type=self.project_type,
        )

    def mark_feature_passed(self, sprint_num: int) -> None:
        """
        Set passes: true for the feature in the current sprint contract.

        This is the ONLY place in the codebase that modifies 'passes'.
        Integrity rules:
          - Feature count must not change.
          - Feature order and IDs must not change.
          - No field other than 'passes' may be altered.
        """
        path = ARTIFACTS_DIR / "feature_list.json"
        raw = path.read_text(encoding="utf-8")

        try:
            features = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"INTEGRITY ERROR: feature_list.json is corrupt: {exc}"
            ) from exc

        original_count = len(features)
        original_ids = [f["id"] for f in features]

        # Validate structure before touching anything
        for i, f in enumerate(features):
            missing = REQUIRED_FEATURE_FIELDS - set(f.keys())
            if missing:
                raise RuntimeError(
                    f"INTEGRITY ERROR: feature_list.json[{i}] missing fields {missing} "
                    "before passes update — aborting"
                )

        # Get feature_id from the current sprint contract
        contract_symlink = ARTIFACTS_DIR / "contracts" / f"sprint_{sprint_num:02d}_current"
        contract = json.loads(contract_symlink.read_text(encoding="utf-8"))
        feature_id = contract.get("feature_id")

        if not feature_id:
            raise ValueError(
                f"Contract for sprint {sprint_num:02d} has no 'feature_id' field"
            )

        matched = False
        for feature in features:
            if feature["id"] == feature_id:
                if feature["passes"] is True:
                    logger.warning(
                        "Feature '%s' was already marked passed", feature_id
                    )
                feature["passes"] = True
                matched = True
                break

        if not matched:
            raise ValueError(
                f"feature_id '{feature_id}' not found in feature_list.json"
            )

        # Post-write integrity check
        if len(features) != original_count:
            raise RuntimeError(
                "INTEGRITY VIOLATION: feature count changed during passes update"
            )
        if [f["id"] for f in features] != original_ids:
            raise RuntimeError(
                "INTEGRITY VIOLATION: feature order/IDs changed during passes update"
            )

        path.write_text(
            json.dumps(features, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        logger.info("Marked feature '%s' as passed (sprint %02d)", feature_id, sprint_num)

    def git_commit(self, message: str) -> None:
        """Stage all changes and commit."""
        subprocess.run(["git", "add", "-A"], check=True, capture_output=True)
        result = subprocess.run(
            ["git", "commit", "-m", message],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Not fatal — could be "nothing to commit"
            logger.warning("git commit returned non-zero: %s", result.stderr.strip())
        else:
            logger.info("git commit: %s", message)

    def update_progress(self, sprint_num: int, feature_name: str) -> None:
        """Append a sprint completion entry to progress.md."""
        progress_path = ARTIFACTS_DIR / "progress.md"
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        entry = (
            f"\n### Sprint {sprint_num:02d} — {feature_name}\n"
            f"Completed: {ts}\n"
        )
        with progress_path.open("a", encoding="utf-8") as f:
            f.write(entry)
        logger.info("progress.md updated for sprint %02d", sprint_num)
