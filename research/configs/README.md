# Local Run Configs

Local `aerd run` configs are ignored by git by default. Keep strategy/research and `--train` configs flat in this directory; the CLI flag selects the mode, not subdirectories.

Use `aerd run <config>` for strategy or research sweeps, and `aerd run --train <config>` for ML training configs with train-specific settings under `train:`.

Ignored files are not secret management. Do not put API keys, provider tokens, or credentials directly in local YAMLs or notebooks. Use environment-backed secret references, and do not force-add local configs unless they are intentionally reviewed as tracked artifacts.
