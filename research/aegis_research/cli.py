from __future__ import annotations

import argparse

from research.aegis_research.config import load_experiment_config
from research.aegis_research.experiments import run_experiment


def main() -> None:
    parser = argparse.ArgumentParser(prog="aegis-research")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run an experiment config")
    run_parser.add_argument("config", help="Path to experiment YAML")

    args = parser.parse_args()
    if args.command == "run":
        result = run_experiment(load_experiment_config(args.config))
        report = result["report"]
        print(f"Run: {result['run_dir']}")
        print(f"Status: {report['status']}")
        print("Reason:")
        for reason in report["reasons"]:
            print(f"- {reason}")


if __name__ == "__main__":
    main()
