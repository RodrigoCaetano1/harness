"""
InitializerAgent: bootstraps the project environment from the approved spec.

Produces: init.sh, artifacts/feature_list.json, artifacts/progress.md.
Executes init.sh to verify the environment is functional.
"""

import json
import logging
import re
import subprocess
from pathlib import Path

from agents.base_agent import BaseAgent
from config import Config

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path("prompts")
ARTIFACTS_DIR = Path("artifacts")

REQUIRED_FEATURE_FIELDS = {"id", "name", "category", "description", "user_story", "smoke_criteria", "passes"}


class InitializerAgent:
    """Sets up the project environment from the approved spec."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.agent = BaseAgent(config, role="initializer")

    def initialize(self) -> None:
        """Run the initializer agent, write artifacts, validate, and execute init.sh."""
        spec = BaseAgent.load_file(ARTIFACTS_DIR / "specs" / "spec_current")
        system_prompt = BaseAgent.load_file(PROMPTS_DIR / "initializer.txt")

        user_message = (
            f"SPEC:\n{spec}\n\n"
            f"STACK: {self.config.stack}\n\n"
            "Produce the three files as instructed."
        )
        response = self.agent.call(
            system_prompt=system_prompt,
            user_message=user_message,
            max_tokens=8192,
        )

        self._write_artifacts(response)
        self._validate_feature_list()
        self._run_init_sh()
        logger.info("Initializer complete")

    def _write_artifacts(self, response: str) -> None:
        """Parse agent output blocks and write files to disk."""
        pattern = re.compile(
            r"=== FILE: (.+?) ===\n(.*?)\n=== END ===",
            re.DOTALL,
        )
        matches = pattern.findall(response)
        if not matches:
            raise RuntimeError(
                "Initializer agent output contained no FILE blocks. "
                "Check the prompt or model response."
            )

        for filename, content in matches:
            filename = filename.strip()
            content = content.strip()

            if filename == "feature_list.json":
                path = ARTIFACTS_DIR / "feature_list.json"
            elif filename == "progress.md":
                path = ARTIFACTS_DIR / "progress.md"
            elif filename == "init.sh":
                path = Path("init.sh")
            else:
                logger.warning("Unexpected file from initializer: %s — writing anyway", filename)
                path = Path(filename)

            BaseAgent.write_file(path, content)
            logger.info("Initializer wrote %s", path)

        init_sh = Path("init.sh")
        if init_sh.exists():
            init_sh.chmod(0o755)

    def _validate_feature_list(self) -> None:
        """
        Validate feature_list.json integrity.
        Raises ValueError on any structural problem.
        """
        path = ARTIFACTS_DIR / "feature_list.json"
        if not path.exists():
            raise FileNotFoundError("Initializer did not produce feature_list.json")

        raw = path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"feature_list.json is not valid JSON: {exc}") from exc

        if not isinstance(data, list):
            raise ValueError("feature_list.json must be a JSON array")
        if len(data) == 0:
            raise ValueError("feature_list.json must contain at least one feature")

        for i, feature in enumerate(data):
            missing = REQUIRED_FEATURE_FIELDS - set(feature.keys())
            if missing:
                raise ValueError(
                    f"feature_list.json[{i}] missing required fields: {missing}"
                )
            if feature["passes"] is not False:
                raise ValueError(
                    f"feature_list.json[{i}] (id={feature.get('id')}) "
                    f"must have passes=false on initialization"
                )

        logger.info("feature_list.json validated: %d features", len(data))

    def _run_init_sh(self) -> None:
        """Execute init.sh to bootstrap the development environment."""
        init_sh = Path("init.sh")
        if not init_sh.exists():
            raise FileNotFoundError("init.sh was not produced by the initializer")

        result = subprocess.run(
            ["bash", "init.sh"],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"init.sh failed (exit code {result.returncode}):\n"
                f"STDOUT:\n{result.stdout}\n"
                f"STDERR:\n{result.stderr}"
            )
        logger.info("init.sh executed successfully")
