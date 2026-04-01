"""
BaseAgent: encapsulates isolated, stateless calls to the Anthropic API.

Each invocation is a fresh context window — no state persists between calls.
State is reconstructed from artifact files before each call.
"""

import logging
from pathlib import Path

import anthropic

from config import Config

logger = logging.getLogger(__name__)


class BaseAgent:
    """
    Wraps a single Anthropic API call.
    Each instantiation represents one isolated agent invocation.
    """

    def __init__(self, config: Config, role: str) -> None:
        self.config = config
        self.role = role
        self.client = anthropic.Anthropic()

    def call(
        self,
        system_prompt: str,
        user_message: str,
        max_tokens: int = 8192,
    ) -> str:
        """
        Send a single-turn message to the model.
        Returns the text content of the response.
        Raises on API errors — no silent failures.
        """
        logger.info("Agent '%s' calling model '%s'", self.role, self.config.model)

        response = self.client.messages.create(
            model=self.config.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )

        text_blocks = [b.text for b in response.content if b.type == "text"]
        if not text_blocks:
            raise RuntimeError(
                f"Agent '{self.role}' received no text content from API"
            )

        result = "\n".join(text_blocks)
        logger.debug(
            "Agent '%s' response: %d chars", self.role, len(result)
        )
        return result

    @staticmethod
    def load_file(path: Path) -> str:
        """Read a file and return its text. Raises FileNotFoundError if missing."""
        if not path.exists():
            raise FileNotFoundError(f"Required artifact not found: {path}")
        return path.read_text(encoding="utf-8")

    @staticmethod
    def write_file(path: Path, content: str) -> None:
        """Write text to a file, creating parent directories as needed."""
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    @staticmethod
    def make_symlink(target: Path, link: Path) -> None:
        """Create or replace a symlink at link pointing to target (by name only)."""
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(target.name)
