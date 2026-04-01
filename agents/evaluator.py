"""
EvaluatorAgent: tests sprint implementations via Playwright and scores them.

Produces structured sprint_feedback.json per iteration.
Does NOT modify feature_list.json.
Enforces minimum score of 6/10 per dimension before approving.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from agents.base_agent import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path("prompts")
ARTIFACTS_DIR = Path("artifacts")

SCORE_DIMENSIONS = {"design", "originality", "craft", "functionality"}
MIN_SCORE = 6.0


class EvaluatorAgent:
    """Tests implementations and produces structured feedback."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.agent = BaseAgent(config, role="evaluator")

    def review_contract(self, sprint_num: int, contract_json: str) -> str:
        """
        Review a proposed sprint contract.
        Returns 'Approve' or 'RequestRevision: <feedback>'.
        """
        system_prompt = BaseAgent.load_file(PROMPTS_DIR / "contract_review.txt")
        user_message = (
            f"SPRINT NUMBER: {sprint_num}\n\n"
            f"PROPOSED CONTRACT:\n{contract_json}"
        )
        response = self.agent.call(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=2048,
        )
        logger.info(
            "Evaluator contract review sprint %d: %s",
            sprint_num, response[:80].replace("\n", " "),
        )
        return response

    def evaluate(self, sprint_num: int, iteration: int) -> dict:
        """
        Evaluate the current implementation via Playwright.
        Returns parsed and validated feedback dict.
        Persists feedback to artifacts/feedback/.
        """
        contract_symlink = (
            ARTIFACTS_DIR / "contracts" / f"sprint_{sprint_num:02d}_current"
        )
        contract = BaseAgent.load_file(contract_symlink)
        system_prompt = BaseAgent.load_file(PROMPTS_DIR / "evaluator.txt")

        user_message = (
            f"SPRINT: {sprint_num}\n"
            f"ITERATION: {iteration}\n\n"
            f"CONTRACT:\n{contract}\n\n"
            "Run Playwright tests and produce sprint_feedback.json as specified."
        )
        response = self.agent.call(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=4096,
        )

        feedback = self._extract_json(response, sprint_num, iteration)
        self._validate_and_enforce(feedback)

        feedback_dir = ARTIFACTS_DIR / "feedback"
        feedback_dir.mkdir(parents=True, exist_ok=True)
        feedback_path = (
            feedback_dir / f"sprint_{sprint_num:02d}_iter_{iteration:03d}.json"
        )
        BaseAgent.write_file(
            feedback_path,
            json.dumps(feedback, indent=2, ensure_ascii=False),
        )
        logger.info(
            "Evaluator sprint %d iter %d: approved=%s scores=%s",
            sprint_num, iteration, feedback.get("approved"), feedback.get("scores"),
        )
        return feedback

    def _extract_json(self, response: str, sprint_num: int, iteration: int) -> dict:
        """Extract a JSON object from the evaluator response."""
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            raise RuntimeError(
                f"Evaluator response for sprint {sprint_num} iter {iteration} "
                "contained no JSON block"
            )
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Evaluator JSON parse error sprint {sprint_num} iter {iteration}: {exc}"
            ) from exc

    def _validate_and_enforce(self, feedback: dict) -> None:
        """
        Validate structure and enforce scoring rules.
        Overrides approved=true if any dimension score < MIN_SCORE.
        """
        if "approved" not in feedback:
            raise ValueError("Evaluator feedback missing 'approved' field")

        scores = feedback.get("scores", {})
        missing_dims = SCORE_DIMENSIONS - set(scores.keys())
        if missing_dims:
            raise ValueError(
                f"Evaluator feedback missing score dimensions: {missing_dims}"
            )

        # Enforce: all dimensions must be >= MIN_SCORE to approve
        if feedback["approved"]:
            for dim in SCORE_DIMENSIONS:
                score = float(scores[dim])
                if score < MIN_SCORE:
                    logger.warning(
                        "approved=true overridden: dimension '%s'=%.1f < %.1f",
                        dim, score, MIN_SCORE,
                    )
                    feedback["approved"] = False
                    feedback.setdefault("bugs", []).append(
                        f"Dimension '{dim}' score {score:.1f} is below minimum {MIN_SCORE}"
                    )
                    break

        # Ensure optional fields have defaults
        feedback.setdefault("bugs", [])
        feedback.setdefault("browser_failures", 0)
        feedback.setdefault("human_intervened", False)
        feedback.setdefault("critique", "")
        feedback.setdefault("criteria_results", [])
