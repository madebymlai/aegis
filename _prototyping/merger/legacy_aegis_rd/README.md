# Archived merger-arbitrage prototype

This directory preserves the retired fixed-cash merger prototype, including its
SEC and ECB fetchers, indicator, strategy, generated configs, evaluation scripts,
tests, and prospective-universe note.

It was removed from active Aegis RD discovery on 2026-07-15. The mechanism was
research-worthy, but the implementation was not operationally viable: repeatable
runs depended on flaky long-horizon IBKR historical requests, one unavailable
instrument failed the entire configured universe, and the available data could not
support a survivorship-safe historical evaluation. The archived files are evidence,
not runnable or promoted components.
