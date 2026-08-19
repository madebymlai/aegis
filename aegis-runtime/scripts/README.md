# Manual scripts

This directory is a scratchpad for scripts run manually during development or
investigation. Its contents are disposable and may be changed or deleted at any
time.

Production code, tests, packaging, and automation must never import from or depend
on anything in this directory. Durable behavior belongs in the package; durable test
support belongs under `tests/`.
