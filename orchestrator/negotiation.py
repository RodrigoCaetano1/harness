"""
Negotiation: manages the contract proposal/review cycle between Generator and Evaluator.

- Up to config.max_rodadas_negociacao rounds.
- Contracts are versioned: sprint_{nn}_v{n}.json + symlink sprint_{nn}_current.
- Returns True if approved, False on deadlock.
"""

import json
import logging
from pathlib import Path

from agents.base_agent import BaseAgent
from agents.evaluator import EvaluatorAgent
from agents.generator import GeneratorAgent
from config import Config

logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")


class Negotiation:
    """Runs the contract proposal/review cycle for a single sprint."""

    def __init__(self, config: Config, sprint_num: int) -> None:
        self.config = config
        self.sprint_num = sprint_num
        self.generator = GeneratorAgent(config)
        self.evaluator = EvaluatorAgent(config)

    def run(self) -> bool:
        """
        Negotiate the sprint contract.
        Returns True if contract was approved, False if deadlock after max rounds.
        """
        contracts_dir = ARTIFACTS_DIR / "contracts"
        contracts_dir.mkdir(parents=True, exist_ok=True)

        for round_num in range(1, self.config.max_rodadas_negociacao + 1):
            logger.info(
                "Negotiation sprint %02d round %d/%d",
                self.sprint_num, round_num, self.config.max_rodadas_negociacao,
            )

            # Generator proposes contract
            raw_contract = self.generator.propose_contract(self.sprint_num)

            # Validate JSON
            try:
                contract_data = json.loads(raw_contract)
            except json.JSONDecodeError as exc:
                raise RuntimeError(
                    f"Generator produced non-JSON contract "
                    f"(sprint {self.sprint_num}, round {round_num}): {exc}"
                ) from exc

            # Persist versioned contract
            contract_path = (
                contracts_dir
                / f"sprint_{self.sprint_num:02d}_v{round_num}.json"
            )
            BaseAgent.write_file(
                contract_path,
                json.dumps(contract_data, indent=2, ensure_ascii=False),
            )
            symlink = contracts_dir / f"sprint_{self.sprint_num:02d}_current"
            BaseAgent.make_symlink(contract_path, symlink)
            logger.info("Contract written: %s", contract_path)

            # Evaluator reviews
            review = self.evaluator.review_contract(
                self.sprint_num,
                json.dumps(contract_data, indent=2, ensure_ascii=False),
            )

            if review.strip().startswith("Approve"):
                logger.info(
                    "Contract approved on round %d (sprint %02d)",
                    round_num, self.sprint_num,
                )
                return True

            logger.info(
                "Contract revision requested (round %d): %s",
                round_num, review[:120].replace("\n", " "),
            )
            # Feedback is available via progress.md / contract file on next round

        logger.warning(
            "Negotiation deadlock: sprint %02d after %d rounds",
            self.sprint_num, self.config.max_rodadas_negociacao,
        )
        return False
