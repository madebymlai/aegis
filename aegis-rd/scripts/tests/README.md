# Research artifact checks

These checks execute concrete files under `research/components/` and
`research/configs/`. They are deliberately outside the normal `tests/` Pytest
tree, so experimental research artifacts cannot break the framework suite.

Run them explicitly:

```bash
uv run pytest scripts/tests/components scripts/tests/configs scripts/tests/test_floor_evaluation.py -q
```

Tests for the reusable research framework remain under `tests/`.

Keep the command above in step with the files here. `test_floor_gate.py` used to sit at this
level, was named by neither the default `testpaths` nor this command, and so went unnoticed
for three days after `b1a50e34` deleted the module it imported - the collection error was
never seen because nothing collected it.
