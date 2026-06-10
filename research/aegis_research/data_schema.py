from __future__ import annotations

import hashlib
from typing import Any

import pandas as pd


def index_identity(index: pd.Index) -> dict[str, Any]:
    digest = hashlib.sha256()
    count = 0
    start = None
    end = None
    for value in index:
        text = str(value)
        if count:
            digest.update(b"\n")
        digest.update(text.encode())
        if start is None:
            start = text
        end = text
        count += 1
    return {
        "count": count,
        "start": start,
        "end": end,
        "hash": digest.hexdigest(),
    }
