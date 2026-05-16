from __future__ import annotations

import argparse

from research.aegis_research.config import load_experiment_config
from research.aegis_research.experiments import run_experiment
from research.aegis_research.provenance.recorder import RerunMode


def main() -> None:
    parser = argparse.ArgumentParser(prog="aegis-research")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run an experiment config")
    run_parser.add_argument("config", help="Path to experiment YAML")
    run_parser.add_argument(
        "--rerun-mode",
        choices=[RerunMode.NEW, RerunMode.DUPLICATE, RerunMode.FORK, RerunMode.OVERWRITE],
        default=RerunMode.NEW,
        help="Explicit run creation mode",
    )
    run_parser.add_argument("--run-id", help="Optional physical run id")
    run_parser.add_argument("--parent-run-id", help="Parent run id for forked runs")
    run_parser.add_argument("--supersedes-run-id", help="Prior run id superseded by overwrite mode")

    args = parser.parse_args()
    if args.command == "run":
        result = run_experiment(
            load_experiment_config(args.config),
            rerun_mode=args.rerun_mode,
            run_id=args.run_id,
            parent_run_id=args.parent_run_id,
            supersedes_run_id=args.supersedes_run_id,
        )
        report = result.get("report", {})
        print(f"Run: {result['run_dir']}")
        print(f"Status: {result['status']}")
        if report:
            print("Reason:")
            for reason in report["reasons"]:
                print(f"- {reason}")


if __name__ == "__main__":
    main()
