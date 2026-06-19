"""``aegis-data`` CLI: manage the shared historical-data store.

Commands:
  - ``path``  print the store directory.
  - ``ls``    list cached per-contract parquets for a dataset.
  - ``pull``  fetch a back-adjusted continuous future (via the Nautilus databento
              port), caching each dated contract in the store.
"""

from __future__ import annotations

import argparse
from datetime import date

from aegis_data.source import continuous_panel, databento_contract_calendar, databento_source
from aegis_data.store import data_dir, futures_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="aegis-data", description="Aegis historical market-data store")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("path", help="print the store directory")

    p_ls = sub.add_parser("ls", help="list cached contracts for a dataset")
    p_ls.add_argument("--dataset", default="GLBX.MDP3")

    p_pull = sub.add_parser("pull", help="fetch a back-adjusted continuous future into the store")
    p_pull.add_argument("root", help="contract root, e.g. ES")
    p_pull.add_argument("--dataset", default="GLBX.MDP3")
    p_pull.add_argument("--start", required=True, help="YYYY-MM-DD")
    p_pull.add_argument("--end", required=True, help="YYYY-MM-DD")
    p_pull.add_argument("--method", default="ratio", choices=["ratio", "difference"])
    p_pull.add_argument("--roll-lead-days", type=int, default=5)

    args = parser.parse_args(argv)

    if args.command == "path":
        print(data_dir())
        return 0

    if args.command == "ls":
        directory = futures_dir(args.dataset)
        if not directory.exists():
            print(f"(empty: {directory})")
            return 0
        for parquet in sorted(directory.glob("*.parquet")):
            print(parquet.name)
        return 0

    if args.command == "pull":
        fetch = databento_source(args.dataset)
        list_contracts = databento_contract_calendar(args.dataset)
        panel = continuous_panel(
            args.root,
            date.fromisoformat(args.start),
            date.fromisoformat(args.end),
            fetch=fetch,
            list_contracts=list_contracts,
            method=args.method,
            roll_lead_days=args.roll_lead_days,
        )
        print(
            f"{args.root}: {len(panel)} continuous bars "
            f"{panel.index.min().date()}..{panel.index.max().date()} "
            f"(contracts cached under {futures_dir(args.dataset)})"
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
