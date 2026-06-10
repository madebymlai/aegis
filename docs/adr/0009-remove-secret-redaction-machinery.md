# Remove secret-redaction machinery; keep env-reference resolution

Status: accepted

Aegis RD **Runs** are local and single-machine: run folders, **Manifests**, **Evidence**, and
the native-metadata sidecars never leave the machine that produced them — they are not
committed, shared, or published. The config-contract pattern
(`docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md`,
issue #7) nonetheless built redaction to keep secrets out of *shareable* artifacts — a leak
that cannot occur under this threat model. We remove the redaction machinery and keep only
the `{env: VAR}` → value resolution, which is a genuine mechanism for the credentialed data
source (env-supplied API key) planned next.

Removed: `redact_config`, `redact_text`, `known_config_secret_values`, the inline-credential
rejection (`_validate_no_inline_secrets`) and its `SECRET_KEY_RE` / `SECRET_VALUE_RE`, the
native-artifact byte-scanning and secret-state assertions, the `assert_public_metadata_safe`
gate, the path/home-dir scrubbing, and the `known_secrets` value threaded through the
market-data and provenance layers. Kept and **renamed for truth-in-naming**:
`configuration/secrets.py` → `configuration/env_references.py` (resolution only);
`market_data/safety.py` → `market_data/native_metadata.py` — the allowlist *projection*
survives because it is the native-object serializer (a huge VBT `Data` object → a small
JSON-safe metadata dict), not a secret guard.

## Considered options

- **Remove redaction, keep env-ref resolution** (this decision): the allowlist projection and
  a length cap on diagnostic/error text survive on their own non-secret merits (serialization;
  bounded **Manifests**). A resolved credential may now appear in a local **Manifest** — fine,
  it never leaves the machine.
- **Keep the machinery**: rejected. It guards against publishing secrets in artifacts that are
  never published, and threads `known_secrets` through ~6 functions and two dataclasses
  (`MarketDataAdapterResult`, `MarketDataResult`) for no live benefit.
- **Also drop env-ref resolution (full YAGNI)**: rejected. A credentialed source with an
  env-supplied API key is concretely planned; the `{env: VAR}` form is the boundary that keeps
  the key out of the **Run Config** YAML.

## Consequences

- **No schema bumps.** Config schema stays at v8 (validation is only *loosened*; existing valid
  configs behave identically and the `{env: VAR}` form resolves unchanged), the
  `native_metadata.v1` sidecar shape is unchanged, and the **Manifest** is untouched.
  Credential-free configs (`yf`/`synthetic`/`csv`) hash byte-identically, so no existing **Run**
  changes — `redact_config` was a no-op on them, and resolved secret values never reached disk
  (resolution is ephemeral, at pull-time).
- Inline credentials in YAML are **no longer rejected**; they are accepted and persisted raw,
  locally. Env references remain the documented convention, now by habit rather than regex.
- Remote-pull failures may now **chain the original cause** (`raise ... from error`) for
  debuggability, since there is nothing to leak; diagnostics keep their length clip.
- `ArtifactVisibility.PUBLIC/PRIVATE` becomes write-only and meaningless once nothing is
  published or scrubbed. Its removal is a separate **Manifest**-schema migration, tracked as a
  follow-up (a different concept — publishability, not secrets — and a schema change).
- Secret-behavior tests are deleted; the env-ref *resolution* test is kept (its redaction
  assertion dropped). The `config-contract-security-reproducibility-2026-05-16.md` solution doc
  is amended to mark its secret-safety guidance retired under this ADR.
- **CONTEXT.md is untouched.** "Artifacts stay local" is a threat-model decision (this ADR), not
  a glossary term.
