"""``aegis-data`` CLI for the shared Nautilus catalog."""

from __future__ import annotations

import argparse

from aegis_data.catalog import catalog_root


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="aegis-data",
        description="Inspect the shared Catalog path",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("path", help="print the catalog directory")

    args = parser.parse_args(argv)
    if args.command == "path":
        print(catalog_root())
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
