# Prototype verdict — pydantic v2 vs cattrs for one config section (portfolio)

**Question:** if we port one config section to a validation framework, what does the
real diff look like on (1) SSOT requiredness, (2) all-errors-at-once → our
`ConfigValidationIssue(path, message)` contract, (3) byte-identical `resolved_config`?

Run: `.venv/bin/python research/aegis_research/configuration/_prototype_pydantic_portfolio.py`
(throwaway: `_prototype_pydantic_portfolio.py` + this file. `cattrs` was `uv pip install`'d
into `.venv` for the spike — not added to pyproject.)

## Answer: pydantic v2 is the better fit. Both kill the drift; pydantic wins on the contract.

| Claim | pydantic v2 (`pydantic.dataclasses`, per-field strict) | cattrs (stdlib dataclass + Converter) |
|---|---|---|
| SSOT requiredness (drift killed) | ✅ omit `gross_cap` → `is required` (exact wording) | ✅ → `required field missing @ $.gross_cap` |
| All-errors-at-once | ✅ accumulates | ✅ `detailed_validation` (default) |
| Map to our `(path, message)` | ✅ **clean** — structured `loc` tuple + `type` (`missing`→`is required`) | ⚠️ **messy** — path is baked into the message string (`... @ $.gross_cap`); needs string-parsing |
| Closed-world unknown keys | ✅ `extra="forbid"` | ✅ `forbid_extra_keys=True` |
| Valid input → byte-identical | ✅ | ✅ |
| Strictness vs today | ✅ rejects `bool` as number (matches current) | ❌ **laxer** — `fees: true` silently coerced to `1.0` (current REJECTS); needs custom strict hooks |

## The one real migration gotcha (affects both, inherent to typing a field `float`)

`gross_cap: 1` (YAML integer) **diverges bytes**: today's stdlib dataclass stores the raw
`int` → `"gross_cap":1`; both frameworks coerce int→float → `"gross_cap":1.0`.
Since `resolved_config.v1` is hash-pinned, configs written with integer literals would
re-hash differently after migration.

This also exposes a **latent quirk in today's code**: it serializes an `int` in a field
declared `float`. Cleanest path: fix the current builder to normalize int→float **first**
(one line, regenerate goldens), which makes the framework migration byte-neutral.

## Recommendation

- **pydantic v2** if we go framework: structured errors → trivial issue mapping, strict mode
  matches today's strictness, `@model_validator`/`@field_validator` are the natural home for
  the ~21 bespoke messages + cross-field rules.
- **cattrs** is the weaker pick *here*: error→issue mapping needs string-parsing, and its
  default float coercion is laxer than today (a strictness regression) unless you register
  custom hooks — which erodes its "minimal intrusion" appeal.
- Minor pydantic cleanups for real integration: dedupe tombstone double-report (pop known
  removed keys before pydantic), remap range/enum wording to our strings (or update test
  assertions). All mechanical.

## Still true regardless of framework

- The actual drift is fixed by option B (derive requiredness from `__dataclass_fields__`) in
  one helper, today — no dependency.
- A framework *relocates* (does not delete) the ~983 loc of domain rules; it deletes the
  312-loc `base.py` primitive toolkit. That's the real trade.
- If we proceed with pydantic: write the golden-bytes test on `resolved_config.v1` FIRST
  (lock the oracle), normalize the int→float quirk, then port section-by-section.
