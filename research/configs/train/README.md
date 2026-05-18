# Train Configs

Local `aerd train` configs are ignored by git by default. They select model plugins and label/indicator inputs by trusted IDs and parameters only.

Use `docs/examples/scaffold_experiment_walkthrough.ipynb` for the public runnable training walkthrough. It is scaffold evidence only, not validated trading methodology, empirical edge, or investment advice.

Ignored files are not secret management. Do not put API keys, provider tokens, or credentials directly in train YAMLs or notebooks. Use environment-backed secret references, and do not force-add local train configs unless they are intentionally reviewed as tracked artifacts.
