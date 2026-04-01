"""
main.py — entry point for the autonomous full-stack application harness.

Usage:
  python main.py "your prompt here" --model claude-opus-4-5
  HARNESS_MODEL=claude-opus-4-5 python main.py "your prompt here"

Optional flags:
  --model MODEL           Anthropic model string (required if HARNESS_MODEL not set)
  --project-type TYPE     Tag for Meta-Harness counters (default: "default")
  --no-pause              Skip human approval pause after spec generation
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from agents.generator import GeneratorAgent
from agents.initializer import InitializerAgent
from agents.planner import PlannerAgent
from config import Config
from orchestrator.human_review import HumanReview
from orchestrator.meta_trigger import MetaTrigger
from orchestrator.sprint_loop import SprintLoop

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

ARTIFACTS_DIR = Path("artifacts")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Autonomous full-stack harness",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("prompt", help="Short description of the app to build")
    parser.add_argument(
        "--model",
        help="Anthropic model string (e.g. claude-opus-4-5). "
             "Required if HARNESS_MODEL env var is not set.",
    )
    parser.add_argument(
        "--project-type",
        default="default",
        help="Project type tag for Meta-Harness counters (default: %(default)s)",
    )
    parser.add_argument(
        "--no-pause",
        action="store_true",
        help="Skip human approval pause after spec generation",
    )
    return parser.parse_args()


def build_config(args: argparse.Namespace) -> Config:
    config = Config()
    if args.model:
        config.model = args.model
    config.pausa_pos_spec = not args.no_pause
    config.validate()
    return config


def load_feature_list() -> list:
    path = ARTIFACTS_DIR / "feature_list.json"
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> None:
    args = parse_args()
    config = build_config(args)
    project_type = args.project_type

    logger.info(
        "Harness starting — model: %s | project_type: %s",
        config.model, project_type,
    )

    # ── Step 1: Planner generates spec ─────────────────────────────────────
    planner = PlannerAgent(config)
    spec_path = planner.generate_spec(args.prompt)
    logger.info("Spec generated: %s", spec_path)

    # ── Step 2: Generator reviews spec (max 1 revision round) ──────────────
    generator = GeneratorAgent(config)
    review = generator.review_spec()

    if "SPEC_OK" not in review:
        logger.info("Spec review found issues — requesting Planner revision")
        spec_path = planner.revise_spec(args.prompt, review)
        logger.info("Revised spec: %s", spec_path)
    else:
        logger.info("Spec review: no issues found")

    # ── Step 3: Optional human approval of spec ─────────────────────────────
    if config.pausa_pos_spec:
        human = HumanReview()
        decision = human.prompt(
            sprint=0,
            iteration=0,
            reason="Spec ready — review before initialization begins",
            last_feedbacks=[],
        )
        if decision == "abort":
            logger.info("Operator aborted after spec review")
            sys.exit(0)
        if decision == "adjust_spec":
            logger.info(
                "Operator chose to adjust spec. "
                "Edit artifacts/specs/spec_current, then restart."
            )
            sys.exit(0)

    # ── Step 4: Initializer bootstraps environment ──────────────────────────
    initializer = InitializerAgent(config)
    initializer.initialize()

    # ── Step 5: Sprint loop ─────────────────────────────────────────────────
    features = load_feature_list()
    total_features = len(features)
    sprint_loop = SprintLoop(config, project_type=project_type)
    meta_trigger = MetaTrigger(config)

    for sprint_num, feature in enumerate(features, start=1):
        if feature.get("passes") is True:
            logger.info(
                "Feature '%s' already passed — skipping sprint %02d",
                feature.get("id"), sprint_num,
            )
            continue

        logger.info(
            "Sprint %02d/%02d: %s — %s",
            sprint_num, total_features,
            feature.get("id"), feature.get("name"),
        )

        approved = sprint_loop.run(sprint_num)

        if approved:
            sprint_loop.mark_feature_passed(sprint_num)
            sprint_loop.git_commit(
                f"feat(sprint-{sprint_num:02d}): {feature.get('name', 'feature')}"
            )
            sprint_loop.update_progress(sprint_num, feature.get("name", ""))
            logger.info("Sprint %02d approved and committed", sprint_num)
        else:
            logger.error(
                "Sprint %02d failed — harness stopping after %02d/%02d sprints",
                sprint_num, sprint_num - 1, total_features,
            )
            meta_trigger.record_review(project_type)
            break

    # ── Step 6: Post-execution meta trigger ────────────────────────────────
    meta_trigger.record_execution(project_type)
    if meta_trigger.should_trigger(project_type):
        meta_trigger.run_meta_harness(project_type)

    logger.info("Harness complete")


if __name__ == "__main__":
    main()
