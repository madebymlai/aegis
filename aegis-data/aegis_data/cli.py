"""``aegis-data`` CLI: manage the shared historical-data store.

Commands:
  - ``path``  print the store directory.
  - ``ls``    list cached per-contract parquets for a dataset.
  - ``pull``  fetch a back-adjusted continuous future (via the Nautilus databento
              port), caching each dated contract in the store.
"""

from __future__ import annotations

import argparse
from datetime import date, timedelta

from aegis_data.source import continuous_panel, databento_contract_calendar, databento_leg_ports
from aegis_data.store import data_dir, raw_futures_dir


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

    args = parser.parse_args(argv)

    if args.command == "path":
        print(data_dir())
        return 0

    if args.command == "ls":
        directory = raw_futures_dir(args.dataset)
        if not directory.exists():
            print(f"(empty: {directory})")
            return 0
        for parquet in sorted(directory.glob("*/*.parquet")):
            print(parquet.relative_to(directory))
        return 0

    if args.command == "pull":
        ports = databento_leg_ports(args.dataset)
        list_contracts = databento_contract_calendar(args.dataset)
        panel = continuous_panel(
            args.root,
            date.fromisoformat(args.start),
            date.fromisoformat(args.end),
            ports=ports,
            list_contracts=list_contracts,
            method=args.method,
            bar_cadence=timedelta(days=1),
        )
        print(
            f"{args.root}: {len(panel)} continuous bars "
            f"{panel.index.min().date()}..{panel.index.max().date()} "
            f"(contracts cached under {raw_futures_dir(args.dataset)})"
        )
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
