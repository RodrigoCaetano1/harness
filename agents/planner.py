"""
PlannerAgent: expands a short user prompt into a versioned spec.md.

Versioning: artifacts/specs/spec_v{n}.md + symlink spec_current.
Revision: accepts review feedback and rewrites the spec (up to max_rodadas_revisao_spec times).
"""

import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path("prompts")
ARTIFACTS_DIR = Path("artifacts")


class PlannerAgent:
    """Generates and versions product specification documents."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.agent = BaseAgent(config, role="planner")

    def _next_version(self) -> int:
        specs_dir = ARTIFACTS_DIR / "specs"
        specs_dir.mkdir(parents=True, exist_ok=True)
        existing = list(specs_dir.glob("spec_v*.md"))
        return len(existing) + 1

    def generate_spec(self, user_prompt: str) -> Path:
        """
        Generate a new versioned spec from user_prompt.
        Returns path to the new spec file.
        """
        system_prompt = BaseAgent.load_file(PROMPTS_DIR / "planner.txt")
        response = self.agent.call(
            system_prompt=system_prompt,
            user_message=f"USER PROMPT:\n{user_prompt}",
            max_tokens=8192,
        )

        version = self._next_version()
        spec_path = ARTIFACTS_DIR / "specs" / f"spec_v{version}.md"
        BaseAgent.write_file(spec_path, response)
        BaseAgent.make_symlink(spec_path, ARTIFACTS_DIR / "specs" / "spec_current")

        logger.info("Planner wrote %s", spec_path)
        return spec_path

    def revise_spec(self, user_prompt: str, review_feedback: str) -> Path:
        """
        Revise the current spec incorporating review feedback.
        Returns path to the new spec version.
        """
        current_spec = BaseAgent.load_file(ARTIFACTS_DIR / "specs" / "spec_current")
        system_prompt = BaseAgent.load_file(PROMPTS_DIR / "planner.txt")

        user_message = (
            f"USER PROMPT:\n{user_prompt}\n\n"
            f"CURRENT SPEC:\n{current_spec}\n\n"
            f"REVIEW FEEDBACK — fix all issues listed below:\n{review_feedback}"
        )
        response = self.agent.call(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=8192,
        )

        version = self._next_version()
        spec_path = ARTIFACTS_DIR / "specs" / f"spec_v{version}.md"
        BaseAgent.write_file(spec_path, response)
        BaseAgent.make_symlink(spec_path, ARTIFACTS_DIR / "specs" / "spec_current")

        logger.info("Planner revised spec → %s", spec_path)
        return spec_path
