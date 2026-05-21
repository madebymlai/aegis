# Local Run Configs

Local `aerd run` configs are ignored by git by default. Keep reviewed strategy/research configs flat in this directory; there is no mode selected from subdirectories or CLI flags.

Use `aerd run <config>` for strategy or research sweeps over explicit component/playbook refs.

Run configs can add a top-level `split` block to score the same candidate set through VBT split windows and publish one final split-based leaderboard. `split.method` is the exact `vbt.Splitter` constructor method, and `split.params` are kwargs for that method. Inspect available methods and signature-derived params with `aerd show splitters <method>` before authoring YAML.

```yaml
split:
  method: from_rolling
  params:
    length: 252
    offset: 252
    split: 0.8
    set_labels: [selection, held_out]
  max_splits: 100
```

Compatible VBT splitter methods, such as `from_rolling` and `from_purged_kfold`, use the same run scoring pipeline when VBT can build exactly two non-overlapping sets per split from the source index plus params. The first set is used for selection, the second set is used for held-out scoring, and native VBT set labels are preserved in evidence.

Ignored files are not secret management. Do not put API keys, provider tokens, or credentials directly in local YAMLs or notebooks. Use environment-backed secret references, and do not force-add local configs unless they are intentionally reviewed as tracked artifacts.
