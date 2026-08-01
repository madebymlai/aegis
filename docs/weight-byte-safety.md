# Weight byte-safety check

The check drives the public `ExecutionBundle.compute_weights` seam with a
deterministic native-currency panel and a live FX conversion. It writes the
resulting weight frame with stable labels, timestamps, float formatting, and
line endings. A changed byte means a computed weight or its identity moved.

From the repository root, produce two artifacts from the same revision and
prove that the harness itself is deterministic:

```bash
cd aegis-runtime
uv run python scripts/write_weight_artifact.py /tmp/aegis-weights-1.csv
uv run python scripts/write_weight_artifact.py /tmp/aegis-weights-2.csv
cmp /tmp/aegis-weights-1.csv /tmp/aegis-weights-2.csv
sha256sum /tmp/aegis-weights-1.csv
```

For a before/after check, run the first command in the base-revision checkout,
run the second in the candidate-revision checkout, then compare them with
`cmp`. The command is intentionally independent of the absent shipped bundle
wheels and is cheap enough to run after every ticket in the weight-decision
docket.
