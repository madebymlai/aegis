from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from research.aegis_research.config import (
    DataConfig,
    ExperimentConfig,
    SplitConfig,
    resolve_experiment_config,
)
from research.aegis_research.experiments import run_experiment
from research.aegis_research.provenance.manifest import (
    ArtifactStatus,
    ArtifactVisibility,
    RunManifest,
    validate_manifest,
)
from research.aegis_research.provenance.native import (
    NativeArtifactSafetyError,
    NativeArtifactWriter,
)


def test_native_writer_persists_private_artifact_and_public_metadata(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    writer.write_native_artifact(
        artifact_id="portfolio.split_0.test",
        role="portfolio",
        producer_stage="validation",
        path="native/portfolio.pkl",
        obj=_NativeObject(b"portfolio-bytes"),
        metadata={"split": "split_0", "set": "test"},
    )

    native = next(
        artifact for artifact in manifest.artifacts if artifact["id"] == "portfolio.split_0.test"
    )
    sidecar = next(
        artifact
        for artifact in manifest.artifacts
        if artifact["id"] == "portfolio.split_0.test.metadata"
    )
    assert native["status"] == ArtifactStatus.COMPLETED
    assert native["visibility"] == ArtifactVisibility.PRIVATE
    assert sidecar["status"] == ArtifactStatus.COMPLETED
    assert sidecar["visibility"] == ArtifactVisibility.PUBLIC
    assert sidecar["upstream_artifact_ids"] == []
    assert native["upstream_artifact_ids"] == [sidecar["id"]]
    sidecar_payload = json.loads((tmp_path / sidecar["path"]).read_text())
    assert sidecar_payload["schema_version"] == "native_metadata.v1"
    assert sidecar_payload["metadata"]["split"] == "split_0"
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_native_writer_rejects_path_collision(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)
    target = tmp_path / "native" / "portfolio.pkl"
    target.parent.mkdir()
    target.write_bytes(b"existing")

    with pytest.raises(FileExistsError):
        writer.write_native_artifact(
            artifact_id="portfolio",
            role="portfolio",
            producer_stage="validation",
            path="native/portfolio.pkl",
            obj=_NativeObject(b"new"),
        )


def test_native_writer_fails_closed_when_secret_bytes_are_detected(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"token=super-secret-token"),
            known_secrets=["super-secret-token"],
        )

    artifact = next(artifact for artifact in manifest.artifacts if artifact["id"] == "data.remote")
    assert artifact["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()


def test_native_writer_fails_closed_when_secret_like_bytes_are_detected(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"Authorization: Bearer generated-token"),
        )

    artifact = next(artifact for artifact in manifest.artifacts if artifact["id"] == "data.remote")
    assert artifact["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()


def test_native_writer_rejects_secret_public_metadata(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"safe-bytes"),
            metadata={"api_token": "super-secret-token"},
            known_secrets=["super-secret-token"],
        )

    artifacts = {artifact["id"]: artifact for artifact in manifest.artifacts}
    assert artifacts["data.remote"]["status"] == ArtifactStatus.FAILED
    assert artifacts["data.remote.metadata"]["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_data_native_writer_rejects_secret_sensitive_object_state(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(NativeArtifactSafetyError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data_native",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObjectWithSensitiveState(),
        )

    artifacts = {artifact["id"]: artifact for artifact in manifest.artifacts}
    assert artifacts["data.remote"]["status"] == ArtifactStatus.FAILED
    assert artifacts["data.remote.metadata"]["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


def test_native_writer_fails_sidecar_when_metadata_write_fails(tmp_path: Path) -> None:
    manifest = RunManifest.new(
        run_id="run-1",
        run_dir=tmp_path,
        run_label="baseline",
        mode="new",
        config={},
    )
    writer = NativeArtifactWriter(manifest, tmp_path)

    with pytest.raises(TypeError):
        writer.write_native_artifact(
            artifact_id="data.remote",
            role="data",
            producer_stage="data",
            path="native/data.pkl",
            obj=_NativeObject(b"safe-bytes"),
            metadata={"not_json": object()},
        )

    artifacts = {artifact["id"]: artifact for artifact in manifest.artifacts}
    assert artifacts["data.remote"]["status"] == ArtifactStatus.FAILED
    assert artifacts["data.remote.metadata"]["status"] == ArtifactStatus.FAILED
    assert not (tmp_path / "native" / "data.pkl").exists()
    validate_manifest(manifest.to_dict(), run_dir=tmp_path)


@pytest.mark.parametrize(
    "secret_section", ["wrapper_kwargs", "provider_kwargs", "execution_kwargs"]
)
def test_remote_native_artifact_scans_resolved_remote_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    secret_section: str,
) -> None:
    monkeypatch.setenv("REMOTE_TOKEN", "super-secret-token")
    monkeypatch.setattr("research.aegis_research.data.vbt.YFData", _RemoteDataWithSecret)
    data_kwargs = {
        secret_section: {"api_token": {"env": "REMOTE_TOKEN"}},
    }
    config = resolve_experiment_config(
        ExperimentConfig(
            name="remote-secret-check",
            output_dir=str(tmp_path),
            data=DataConfig(
                source="yfinance",
                symbols=["SYN"],
                start="2020-01-01",
                end="2021-01-01",
                timeframe="1D",
                **data_kwargs,
            ),
        )
    )

    with pytest.raises(NativeArtifactSafetyError):
        run_experiment(config, run_id="remote-run")

    run_dir = tmp_path / "remote-run"
    payload = json.loads((run_dir / "manifest.json").read_text())
    artifacts = {artifact["id"]: artifact for artifact in payload["artifacts"]}
    assert artifacts["data.metadata"]["status"] == ArtifactStatus.COMPLETED
    assert artifacts["data.native"]["status"] == ArtifactStatus.FAILED
    assert not (run_dir / "native" / "data.pkl").exists()
    assert "super-secret-token" not in json.dumps(payload)


def test_indicator_native_artifact_uses_private_bundle_and_public_sidecar(tmp_path: Path) -> None:
    config = resolve_experiment_config(
        ExperimentConfig(
            name="indicator-native-check",
            output_dir=str(tmp_path),
            data=DataConfig(source="synthetic", symbols=["SYN"], rows=180),
            split=SplitConfig(diagnostic_validation_allowed=True),
        )
    )

    result = run_experiment(config, run_id="indicator-native-run")

    run_dir = Path(result["run_dir"])
    payload = json.loads((run_dir / "manifest.json").read_text())
    artifacts = {artifact["id"]: artifact for artifact in payload["artifacts"]}
    sidecar = json.loads((run_dir / "native" / "indicators.pkl.metadata.json").read_text())

    assert artifacts["indicators.native"]["visibility"] == ArtifactVisibility.PRIVATE
    assert artifacts["indicators.native.metadata"]["visibility"] == ArtifactVisibility.PUBLIC
    assert artifacts["indicators.native"]["status"] == ArtifactStatus.COMPLETED
    assert "ma" in sidecar["metadata"]["native_object_ids"]
    assert "rsi" in sidecar["metadata"]["native_object_ids"]
    assert "/home/" not in json.dumps(sidecar)


class _NativeObject:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(self.payload)


class _NativeObjectWithSensitiveState:
    def __init__(self) -> None:
        self.headers = {"X-Session": "generated-cookie"}

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(b"safe-bytes")


class _RemoteDataWithSecret:
    def __init__(self, api_token: str) -> None:
        self.api_token = api_token

    @classmethod
    def pull(
        cls,
        _symbols,
        *,
        api_token: str | None = None,
        wrapper_kwargs: dict | None = None,
        execute_kwargs: dict | None = None,
        **_kwargs,
    ):
        api_token = api_token or (wrapper_kwargs or {}).get("api_token")
        api_token = api_token or (execute_kwargs or {}).get("api_token")
        return cls(api_token)

    def get(self, feature=None, **_kwargs) -> pd.DataFrame:
        index = pd.date_range("2020-01-01", periods=180, freq="1D", tz="UTC", name="Open time")
        frame = pd.DataFrame(
            {
                "Open": range(180),
                "High": [value + 1 for value in range(180)],
                "Low": range(180),
                "Close": [value + 0.5 for value in range(180)],
                "Volume": [1000] * 180,
            },
            index=index,
        )
        frame.columns = pd.MultiIndex.from_product(
            [["SYN"], frame.columns], names=["symbol", "feature"]
        )
        if feature is not None:
            return frame.xs(feature, axis=1, level="feature")
        return frame

    def save(self, path: str | Path) -> None:
        Path(path).write_bytes(f"token={self.api_token}".encode())
