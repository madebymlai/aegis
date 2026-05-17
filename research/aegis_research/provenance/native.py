from __future__ import annotations

import hashlib
import os
import pickle
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

from research.aegis_research.config import SECRET_KEY_RE, SECRET_VALUE_RE
from research.aegis_research.provenance.artifacts import ArtifactRegistry
from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    ArtifactVisibility,
    RunManifest,
    atomic_write_json,
    normalize_artifact_path,
)


class NativeArtifactSafetyError(ValueError):
    pass


DENIED_NATIVE_STATE_KEYS = {
    "auth",
    "authorization",
    "client",
    "cookie",
    "cookies",
    "header",
    "headers",
    "session",
}
SECRET_LIKE_BYTE_MARKERS = (
    b"api_key",
    b"authorization",
    b"bearer ",
    b"basic ",
    b"cookie",
    b"headers",
    b"password",
    b"private key",
    b"secret=",
    b"token=",
)


class NativeArtifactWriter:
    def __init__(
        self,
        manifest: RunManifest,
        run_dir: str | Path,
        *,
        persist: Callable[[], None] | None = None,
    ) -> None:
        self.manifest = manifest
        self.run_dir = Path(run_dir)
        self.registry = ArtifactRegistry(manifest, self.run_dir, persist=persist)

    def write_native_artifact(
        self,
        *,
        artifact_id: str,
        role: str,
        producer_stage: str,
        path: str,
        obj: Any,
        schema_version: str = "native.v1",
        metadata: dict[str, Any] | None = None,
        known_secrets: list[str] | tuple[str, ...] = (),
    ) -> None:
        path = normalize_artifact_path(path)
        final_path = self.run_dir / path
        if final_path.exists():
            raise FileExistsError(f"Native artifact path already exists: {final_path}")

        sidecar_id = f"{artifact_id}.metadata"
        sidecar_path = f"{path}.metadata.json"
        self.registry.plan_artifact(
            artifact_id=artifact_id,
            role=role,
            artifact_type="native_vectorbt",
            producer_stage=producer_stage,
            path=path,
            schema_version=schema_version,
            visibility=ArtifactVisibility.PRIVATE,
            upstream_artifact_ids=[sidecar_id],
            metadata={"metadata_artifact_id": sidecar_id},
        )
        self.registry.plan_artifact(
            artifact_id=sidecar_id,
            role=f"{role}_metadata",
            artifact_type="json",
            producer_stage=producer_stage,
            path=sidecar_path,
            schema_version="native_metadata.v1",
            visibility=ArtifactVisibility.PUBLIC,
            metadata={"native_artifact_id": artifact_id},
        )

        self.registry.begin_artifact_write(artifact_id)
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = _temp_path(final_path)
        try:
            _assert_no_native_secret_state(
                obj,
                known_secrets,
                required=role == "data_native",
            )
            _save_native_object(obj, temp_path)
            content_hash, size = _scan_native_artifact(temp_path, known_secrets)
            temp_path.replace(final_path)
            _fsync_parent(final_path)

            sidecar_payload = {
                "schema_version": "native_metadata.v1",
                "artifact_id": artifact_id,
                "object_type": f"{type(obj).__module__}.{type(obj).__qualname__}",
                "native_artifact_path": path,
                "metadata": metadata or {},
            }
            _assert_no_secret_material(sidecar_payload, known_secrets)
            self.registry.begin_artifact_write(sidecar_id)
            sidecar_full_path = self.run_dir / sidecar_path
            atomic_write_json(sidecar_full_path, sidecar_payload)
            self.registry.complete_existing_file(sidecar_id)
            self.registry.complete_artifact(
                artifact_id,
                content_hash=content_hash,
                size=size,
                metadata={"metadata_artifact_id": sidecar_id, **(metadata or {})},
            )
        except Exception as error:
            if temp_path.exists():
                temp_path.unlink()
            if final_path.exists() and not any(
                artifact["id"] == artifact_id and artifact["status"] == "completed"
                for artifact in self.manifest.artifacts
            ):
                final_path.unlink()
            self._fail_uncompleted_artifact(
                sidecar_id,
                {"error_type": type(error).__name__, "message": "native metadata write failed"},
            )
            self.registry.fail_artifact(
                artifact_id,
                {"error_type": type(error).__name__, "message": "native artifact write failed"},
            )
            raise

    def _fail_uncompleted_artifact(self, artifact_id: str, diagnostic: dict[str, str]) -> None:
        artifact = next(
            (artifact for artifact in self.manifest.artifacts if artifact["id"] == artifact_id),
            None,
        )
        if artifact is not None and artifact["status"] != ArtifactStatus.COMPLETED:
            self.registry.fail_artifact(artifact_id, diagnostic)


def _save_native_object(obj: Any, path: Path) -> None:
    if hasattr(obj, "save"):
        obj.save(path)
        return
    with path.open("wb") as handle:
        pickle.dump(obj, handle)


def _scan_native_artifact(
    path: Path,
    known_secrets: list[str] | tuple[str, ...],
) -> tuple[str, int]:
    known_secret_bytes = tuple(secret.encode() for secret in known_secrets if secret)
    needles = known_secret_bytes + SECRET_LIKE_BYTE_MARKERS
    overlap_size = max((len(needle) for needle in needles), default=1) - 1
    overlap = b""
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
            window = overlap + chunk
            for secret in known_secret_bytes:
                if secret in window:
                    raise NativeArtifactSafetyError("native artifact bytes contain a known secret")
            lowered = window.lower()
            for marker in SECRET_LIKE_BYTE_MARKERS:
                if marker in lowered:
                    raise NativeArtifactSafetyError("native artifact bytes contain secret-like material")
            overlap = window[-overlap_size:] if overlap_size else b""
    return digest.hexdigest(), size


def _assert_no_native_secret_state(
    obj: Any,
    known_secrets: list[str] | tuple[str, ...],
    *,
    required: bool,
) -> None:
    if (required or known_secrets) and hasattr(obj, "__dict__"):
        _assert_no_secret_material(vars(obj), known_secrets)


def _assert_no_secret_material(
    value: Any,
    known_secrets: list[str] | tuple[str, ...],
    *,
    path: str = "$",
) -> None:
    if isinstance(value, str):
        if any(secret and secret in value for secret in known_secrets) or SECRET_VALUE_RE.search(value):
            raise NativeArtifactSafetyError(f"native metadata contains secret material at {path}")
        return
    if isinstance(value, bytes):
        if any(secret and secret.encode() in value for secret in known_secrets):
            raise NativeArtifactSafetyError(f"native state contains known secret bytes at {path}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            if SECRET_KEY_RE.search(key_text) or key_text.lower() in DENIED_NATIVE_STATE_KEYS:
                raise NativeArtifactSafetyError(f"native metadata contains secret key at {path}.{key_text}")
            _assert_no_secret_material(item, known_secrets, path=f"{path}.{key_text}")
        return
    if isinstance(value, list | tuple | set):
        for index, item in enumerate(value):
            _assert_no_secret_material(item, known_secrets, path=f"{path}[{index}]")


def _temp_path(final_path: Path) -> Path:
    with tempfile.NamedTemporaryFile(
        "wb",
        dir=final_path.parent,
        prefix=f"tmp_{final_path.stem}_",
        suffix=final_path.suffix,
        delete=False,
    ) as handle:
        temp_path = Path(handle.name)
    temp_path.chmod(0o600)
    return temp_path


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
