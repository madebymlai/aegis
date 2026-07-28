# Remove secret-redaction and environment-reference machinery

Status: accepted

Aegis RD **Runs** are local and single-machine: run folders, **Manifests**, **Evidence**, and
the native-metadata sidecars never leave the machine that produced them — they are not
committed, shared, or published. The config-contract pattern
(`docs/solutions/architecture-patterns/config-contract-security-reproducibility-2026-05-16.md`,
issue #7) nonetheless built redaction to keep secrets out of *shareable* artifacts — a leak
that cannot occur under this threat model. We remove the redaction machinery and the unused
`{env: VAR}` → value resolution. Credential and provider concerns belong behind Aegis Data;
RD's inert Run Config does not need a credential-reference language.

Removed: `redact_config`, `redact_text`, `known_config_secret_values`, the inline-credential
rejection (`_validate_no_inline_secrets`) and its `SECRET_KEY_RE` / `SECRET_VALUE_RE`, the
native-artifact byte-scanning and secret-state assertions, the `assert_public_metadata_safe`
gate, the path/home-dir scrubbing, and the `known_secrets` value threaded through the
market-data and provenance layers. Also removed: `configuration/env_references.py` and its
public `resolve_env_refs` export. Kept and **renamed for truth-in-naming**:
`market_data/safety.py` → `market_data/native_metadata.py` — the allowlist *projection*
survives because it is the native-object serializer (a huge VBT `Data` object → a small
JSON-safe metadata dict), not a secret guard.

## Considered options

- **Remove redaction and env-ref resolution** (this decision): the allowlist projection and
  a length cap on diagnostic/error text survive on their own non-secret merits (serialization;
  bounded **Manifests**). Credentials are a provider concern behind Aegis Data, not an RD
  configuration concern.
- **Keep the machinery**: rejected. It guards against publishing secrets in artifacts that are
  never published, and threads `known_secrets` through ~6 functions and two dataclasses
  (`MarketDataAdapterResult`, `MarketDataResult`) for no live benefit.
- **Keep env-ref resolution**: rejected. No RD production caller uses it, and the previously
  planned credentialed RD source is no longer part of the architecture.

## Consequences

- **No schema bumps.** Config schema stays at v8, the
  `native_metadata.v1` sidecar shape is unchanged, and the **Manifest** is untouched.
  Credential-free configs (`yf`/`synthetic`/`csv`) hash byte-identically, so no existing **Run**
  changes — `redact_config` was a no-op on them, and resolved secret values never reached disk
  (resolution is ephemeral, at pull-time).
- Inline credentials in YAML are **no longer rejected**; they are accepted and persisted raw,
  locally. Run Configs have no special environment-reference form.
- Remote-pull failures may now **chain the original cause** (`raise ... from error`) for
  debuggability, since there is nothing to leak; diagnostics keep their length clip.
- `ArtifactVisibility.PUBLIC/PRIVATE` becomes write-only and meaningless once nothing is
  published or scrubbed. Its removal is a separate **Manifest**-schema migration, tracked as a
  follow-up (a different concept — publishability, not secrets — and a schema change).
- Secret-behavior and env-ref resolution tests are deleted. The
  `config-contract-security-reproducibility-2026-05-16.md` solution doc
  is amended to mark its secret-safety guidance retired under this ADR.
- The environment-state wording in `CONTEXT.md`'s **Manifest** definition is removed with the
  unused provenance probes. "Artifacts stay local" remains a threat-model decision, not a
  glossary term.
