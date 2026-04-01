"""
IterationTracker: manages the generate → evaluate loop within a single sprint.

Enforces the dynamic iteration threshold, distinguishes browser failures
from implementation failures, and escalates to human_review when needed.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, List

from orchestrator.stats import Stats

if TYPE_CHECKING:
    from agents.evaluator import EvaluatorAgent
    from agents.generator import GeneratorAgent
    from orchestrator.human_review import HumanReview

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")
BROWSER_FAILURE_ESCALATION_THRESHOLD = 2


class IterationTracker:
    """Runs the generate → evaluate loop for a single sprint."""

    def __init__(self, sprint_num: int, config, stats: Stats) -> None:
        self.sprint_num = sprint_num
        self.config = config
        self.stats = stats

    def run(
        self,
        generator: "GeneratorAgent",
        evaluator: "EvaluatorAgent",
        human_review: "HumanReview",
        project_type: str,
    ) -> bool:
        """
        Iterate until approved, threshold exceeded, or human aborts.
        Returns True if sprint was approved.
        """
        threshold = self.stats.compute_threshold(self.sprint_num)
        last_feedbacks: List[dict] = []
        cumulative_browser_failures = 0

        for iteration in range(1, threshold + 1):
            logger.info(
                "Sprint %02d | Iteration %d/%d",
                self.sprint_num, iteration, threshold,
            )

            feedback_path = self._feedback_path(iteration - 1) if iteration > 1 else None

            # --- Generate ---
            try:
                generator.implement(self.sprint_num, feedback_path=feedback_path)
            except Exception as exc:
                logger.error("Generator raised exception: %s", exc)
                self.stats.log_iteration(
                    sprint=self.sprint_num,
                    iteration=iteration,
                    scores={},
                    approved=False,
                    human_intervened=False,
                    browser_failures=0,
                    project_type=project_type,
                )
                raise

            # --- Evaluate ---
            browser_failures_this_iter = 0
            try:
                feedback = evaluator.evaluate(self.sprint_num, iteration)
                browser_failures_this_iter = feedback.get("browser_failures", 0)
            except Exception as exc:
                logger.error("Evaluator raised exception: %s", exc)
                browser_failures_this_iter = 1
                feedback = {
                    "approved": False,
                    "bugs": [f"Evaluator error: {exc}"],
                    "scores": {
                        "design": 0.0,
                        "originality": 0.0,
                        "craft": 0.0,
                        "functionality": 0.0,
                    },
                    "browser_failures": browser_failures_this_iter,
                    "human_intervened": False,
                    "critique": str(exc),
                }

            cumulative_browser_failures += browser_failures_this_iter
            last_feedbacks.append(feedback)

            self.stats.log_iteration(
                sprint=self.sprint_num,
                iteration=iteration,
                scores=feedback.get("scores", {}),
                approved=feedback.get("approved", False),
                human_intervened=feedback.get("human_intervened", False),
                browser_failures=browser_failures_this_iter,
                project_type=project_type,
            )

            if feedback.get("approved"):
                logger.info(
                    "Sprint %02d approved on iteration %d", self.sprint_num, iteration
                )
                return True

            # --- Browser failure escalation ---
            if cumulative_browser_failures >= BROWSER_FAILURE_ESCALATION_THRESHOLD:
                logger.warning(
                    "Sprint %02d: %d cumulative browser failures — escalating",
                    self.sprint_num, cumulative_browser_failures,
                )
                decision = human_review.prompt(
                    sprint=self.sprint_num,
                    iteration=iteration,
                    reason=f"{cumulative_browser_failures} browser failures in this sprint",
                    last_feedbacks=last_feedbacks[-3:],
                )
                self.stats.log_iteration(
                    sprint=self.sprint_num,
                    iteration=iteration,
                    scores=feedback.get("scores", {}),
                    approved=False,
                    human_intervened=True,
                    browser_failures=browser_failures_this_iter,
                    project_type=project_type,
                )
                if decision == "approve":
                    return True
                if decision == "abort":
                    return False
                cumulative_browser_failures = 0  # reset counter after human review

        # --- Threshold exceeded ---
        logger.warning(
            "Sprint %02d: iteration threshold %d exceeded",
            self.sprint_num, threshold,
        )
        decision = human_review.prompt(
            sprint=self.sprint_num,
            iteration=threshold,
            reason=f"Iteration threshold ({threshold}) exceeded",
            last_feedbacks=last_feedbacks[-3:],
        )
        self.stats.log_iteration(
            sprint=self.sprint_num,
            iteration=threshold,
            scores=last_feedbacks[-1].get("scores", {}) if last_feedbacks else {},
            approved=False,
            human_intervened=True,
            browser_failures=0,
            project_type=project_type,
        )
        if decision == "approve":
            return True
        return False

    def _feedback_path(self, iteration: int) -> Path:
        return (
            ARTIFACTS_DIR
            / "feedback"
            / f"sprint_{self.sprint_num:02d}_iter_{iteration:03d}.json"
        )
