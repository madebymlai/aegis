from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any

from research.aegis_research.configuration.schema import (
    SECRET_KEY_RE,
    SECRET_VALUE_RE,
    ConfigValidationError,
    ConfigValidationIssue,
)


def _validate_no_inline_secrets(path: str, value: Any, issues: list[ConfigValidationIssue]) -> None:
    if _is_secret_ref(value):
        env_name = value["env"]
        if not isinstance(env_name, str) or not env_name.strip():
            issues.append(
                ConfigValidationIssue(
                    path, "env secret reference must name an environment variable"
                )
            )
        return
    if isinstance(value, dict):
        for key, item in value.items():
            child_path = f"{path}.{key}"
            if SECRET_KEY_RE.search(str(key)) and not _is_secret_ref(item):
                issues.append(
                    ConfigValidationIssue(
                        child_path,
                        "inline credentials are not allowed; use an env secret reference",
                    )
                )
            _validate_no_inline_secrets(child_path, item, issues)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_no_inline_secrets(f"{path}[{index}]", item, issues)
        return
    if isinstance(value, str) and SECRET_VALUE_RE.search(value):
        issues.append(
            ConfigValidationIssue(path, "secret-like values must be expressed as env references")
        )

def _is_secret_ref(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"env"}


def resolve_secret_refs(value: Any, path: str = "$") -> tuple[Any, list[str]]:
    issues: list[ConfigValidationIssue] = []
    resolved, secrets = _resolve_secret_refs(path, value, issues)
    if issues:
        raise ConfigValidationError(issues)
    return resolved, secrets


def _resolve_secret_refs(
    path: str,
    value: Any,
    issues: list[ConfigValidationIssue],
) -> tuple[Any, list[str]]:
    if _is_secret_ref(value):
        env_name = value["env"]
        secret = os.environ.get(env_name, "")
        if not secret:
            issues.append(
                ConfigValidationIssue(path, f"environment variable {env_name!r} is not set")
            )
            return None, []
        return secret, [secret]
    if isinstance(value, dict):
        resolved: dict[str, Any] = {}
        secrets: list[str] = []
        for key, item in value.items():
            resolved_item, item_secrets = _resolve_secret_refs(f"{path}.{key}", item, issues)
            resolved[key] = resolved_item
            secrets.extend(item_secrets)
        return resolved, secrets
    if isinstance(value, list):
        resolved_list = []
        secrets = []
        for index, item in enumerate(value):
            resolved_item, item_secrets = _resolve_secret_refs(f"{path}[{index}]", item, issues)
            resolved_list.append(resolved_item)
            secrets.extend(item_secrets)
        return resolved_list, secrets
    return value, []


def redact_config(value: Any) -> Any:
    if _is_secret_ref(value):
        return {"env": "<redacted>"}
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if SECRET_KEY_RE.search(str(key)):
                redacted[key] = {"env": "<redacted>"} if _is_secret_ref(item) else "<redacted>"
            else:
                redacted[key] = redact_config(item)
        return redacted
    if isinstance(value, list):
        return [redact_config(item) for item in value]
    if isinstance(value, str) and SECRET_VALUE_RE.search(value):
        return "<redacted>"
    return value


def redact_text(text: str, secrets: list[str] | tuple[str, ...] = ()) -> str:
    redacted = text
    for secret in secrets:
        if secret:
            redacted = redacted.replace(secret, "<redacted>")
    return SECRET_VALUE_RE.sub("<redacted>", redacted)


def known_config_secret_values(value: Any) -> tuple[str, ...]:
    secrets: list[str] = []
    _collect_known_config_secret_values(value, secrets)
    return tuple(secrets)


def _collect_known_config_secret_values(value: Any, secrets: list[str]) -> None:
    if isinstance(value, dict) and set(value) == {"env"}:
        secret = os.environ.get(str(value["env"]), "")
        if secret:
            secrets.append(secret)
        return
    if isinstance(value, dict):
        for item in value.values():
            _collect_known_config_secret_values(item, secrets)
        return
    if isinstance(value, list):
        for item in value:
            _collect_known_config_secret_values(item, secrets)


def to_builtin(value: Any) -> Any:
    if value.__class__.__name__ == "ResolvedLaneConfig":
        return to_builtin(asdict(value.config))
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, dict):
        return {str(k): to_builtin(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_builtin(v) for v in value]
    return value
