"""
GeneratorAgent: implements features per sprint contract and proposes contracts.

Responsibilities:
- Spec review (critical analysis before implementation begins)
- Contract proposal (for negotiation)
- Feature implementation (with or without prior feedback)

Does NOT modify feature_list.json — that is the orchestrator's exclusive responsibility.
"""

import logging
from pathlib import Path
from typing import Optional

from agents.base_agent import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path("prompts")
ARTIFACTS_DIR = Path("artifacts")


class GeneratorAgent:
    """Implements features and participates in contract negotiation."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.agent = BaseAgent(config, role="generator")

    def review_spec(self) -> str:
        """
        Critically review the current spec.
        Returns raw review text (may contain 'SPEC_OK' or a PROBLEMS list).
        """
        spec = BaseAgent.load_file(ARTIFACTS_DIR / "specs" / "spec_current")
        system_prompt = BaseAgent.load_file(PROMPTS_DIR / "spec_review.txt")

        response = self.agent.call(
            system_prompt=system_prompt,
            user_message=f"SPEC TO REVIEW:\n{spec}",
            max_tokens=4096,
        )
        logger.info("Generator spec review complete (%d chars)", len(response))
        return response

    def propose_contract(self, sprint_num: int) -> str:
        """
        Propose a sprint contract for the next unimplemented feature.
        Returns contract as a JSON string.
        """
        spec = BaseAgent.load_file(ARTIFACTS_DIR / "specs" / "spec_current")
        feature_list = BaseAgent.load_file(ARTIFACTS_DIR / "feature_list.json")
        progress = BaseAgent.load_file(ARTIFACTS_DIR / "progress.md")
        system_prompt = BaseAgent.load_file(PROMPTS_DIR / "contract_propose.txt")

        user_message = (
            f"SPEC:\n{spec}\n\n"
            f"FEATURE LIST:\n{feature_list}\n\n"
            f"PROGRESS:\n{progress}\n\n"
            f"SPRINT NUMBER: {sprint_num}\n\n"
            "Propose a sprint contract for the next feature with passes: false."
        )
        response = self.agent.call(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=4096,
        )
        return response

    def implement(
        self,
        sprint_num: int,
        feedback_path: Optional[Path] = None,
    ) -> None:
        """
        Implement the current sprint contract.
        If feedback_path is provided and exists, use the with-feedback prompt.
        """
        spec = BaseAgent.load_file(ARTIFACTS_DIR / "specs" / "spec_current")
        feature_list = BaseAgent.load_file(ARTIFACTS_DIR / "feature_list.json")
        progress = BaseAgent.load_file(ARTIFACTS_DIR / "progress.md")

        contract_symlink = (
            ARTIFACTS_DIR / "contracts" / f"sprint_{sprint_num:02d}_current"
        )
        contract = BaseAgent.load_file(contract_symlink)

        if feedback_path and feedback_path.exists():
            feedback = BaseAgent.load_file(feedback_path)
            system_prompt = BaseAgent.load_file(
                PROMPTS_DIR / "generator_with_feedback.txt"
            )
            user_message = (
                f"SPEC:\n{spec}\n\n"
                f"FEATURE LIST (DO NOT MODIFY):\n{feature_list}\n\n"
                f"CONTRACT:\n{contract}\n\n"
                f"PROGRESS:\n{progress}\n\n"
                f"PRIOR FEEDBACK:\n{feedback}"
            )
            logger.info(
                "Generator implementing sprint %d with feedback", sprint_num
            )
        else:
            system_prompt = BaseAgent.load_file(PROMPTS_DIR / "generator.txt")
            user_message = (
                f"SPEC:\n{spec}\n\n"
                f"FEATURE LIST (DO NOT MODIFY):\n{feature_list}\n\n"
                f"CONTRACT:\n{contract}\n\n"
                f"PROGRESS:\n{progress}"
            )
            logger.info("Generator implementing sprint %d (first attempt)", sprint_num)

        self.agent.call(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=16384,
        )
        logger.info("Generator implementation complete for sprint %d", sprint_num)
