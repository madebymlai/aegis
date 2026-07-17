# Research artifact checks

These checks execute concrete files under `research/components/` and
`research/configs/`. They are deliberately outside the normal `tests/` Pytest
tree, so experimental research artifacts cannot break the framework suite.

Run them explicitly:

```bash
uv run pytest scripts/tests/components scripts/tests/configs -q
```

Tests for the reusable research framework remain under `tests/`.
