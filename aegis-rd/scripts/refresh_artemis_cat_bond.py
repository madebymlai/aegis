"""Refresh the immutable Artemis cat-bond carry snapshot."""

from pathlib import Path

from research.aegis_research.external_data.artemis import refresh_snapshot

if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(refresh_snapshot(root / "research" / "data" / "artemis"))
