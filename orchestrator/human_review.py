"""
HumanReview: pauses the harness and prompts the operator for a decision.

Presents sprint state, last feedbacks, and reason for escalation.
Returns a decision string that the caller acts on.
"""

import logging
from typing import List

logger = logging.getLogger(__name__)

VALID_DECISIONS = frozenset(
    {"continue", "approve", "rewrite_contract", "adjust_spec", "abort"}
)


class HumanReview:
    """Presents state to a human operator and waits for a decision."""

    def prompt(
        self,
        sprint: int,
        iteration: int,
        reason: str,
        last_feedbacks: List[dict],
    ) -> str:
        """
        Display context and collect human decision via stdin.

        Returns one of:
          'continue'         — allow more iterations
          'approve'          — force-approve this sprint
          'rewrite_contract' — operator will manually edit the sprint contract
          'adjust_spec'      — operator will modify the spec
          'abort'            — abort the entire harness
        """
        print()
        print("=" * 64)
        print("  ⚠  HUMAN REVIEW REQUIRED")
        print("=" * 64)
        print(f"  Sprint   : {sprint}")
        print(f"  Iteration: {iteration}")
        print(f"  Reason   : {reason}")
        print("-" * 64)

        if last_feedbacks:
            print("  Recent feedback:")
            for i, fb in enumerate(last_feedbacks, 1):
                scores = fb.get("scores", {})
                bugs = fb.get("bugs", [])
                score_str = "  ".join(
                    f"{k}={v}" for k, v in scores.items()
                )
                print(f"    [{i}] approved={fb.get('approved')}  {score_str}")
                for bug in bugs[:2]:
                    print(f"         • {bug}")

        print("-" * 64)
        print("  Decisions:")
        print("    continue          — allow more iterations")
        print("    approve           — force-approve this sprint")
        print("    rewrite_contract  — manually rewrite the sprint contract file")
        print("    adjust_spec       — manually edit the spec file")
        print("    abort             — stop the harness")
        print("=" * 64)

        while True:
            try:
                raw = input("  Decision: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                raw = "abort"

            if raw in VALID_DECISIONS:
                logger.info(
                    "Human decision: '%s' (sprint=%d, iteration=%d, reason='%s')",
                    raw, sprint, iteration, reason,
                )
                return raw

            print(
                f"  Invalid input '{raw}'. "
                f"Choose from: {', '.join(sorted(VALID_DECISIONS))}"
            )
