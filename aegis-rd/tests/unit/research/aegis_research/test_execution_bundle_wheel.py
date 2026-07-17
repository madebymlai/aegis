import json
import sys
import zipfile

import pytest
from aegis_runtime import (
    BundleManifest,
    ComponentSpec,
    DataContract,
    DriftBand,
    InstrumentId,
    LockedExecutionPlan,
    MissingIndexPolicy,
)
from aegis_runtime.bundle_loader import BUNDLE_PAYLOAD_SCHEMA_VERSION

from research.aegis_research.execution_bundle import BundleArtifact
from research.aegis_research.execution_bundle_wheel import (
    BundleManifestReadError,
    BundleNameCollisionError,
    write_wheel,
)


def _artifact(
    *, candidate_key: str = "0123456789abcdef", version: str = "1.2.3"
) -> BundleArtifact:
    candidate_prefix = candidate_key[:8]
    package_name = f"aegis_exec_tests_strategy_{candidate_prefix}"
    dist_name = f"aegis-exec-tests-strategy-{candidate_prefix}"
    instrument_id = InstrumentId.from_str("AAPL.NASDAQ")
    strategy = ComponentSpec(
        family="strategies",
        component_id="tests.strategy",
        module=f"{package_name}.strategy",
        input_names=("Close",),
        output_names=("target_weights",),
        params={"window": 5},
    )
    return BundleArtifact(
        strategy_id="tests.strategy",
        candidate_key=candidate_key,
        version=version,
        dist_name=dist_name,
        package_name=package_name,
        wheel_filename=f"{dist_name.replace('-', '_')}-{version}-py3-none-any.whl",
        contract=DataContract(
            instrument_ids=(instrument_id,),
            required_arrays=("Close",),
            base_currency="EUR",
            timeframe="1D",
            missing_index=MissingIndexPolicy.DROP,
            lookback_bars=5,
        ),
        manifest=BundleManifest(
            run_id="run-1",
            role="best",
            candidate_key=candidate_key,
            component_source_hashes={"strategies/tests.strategy": "abc123"},
            instrument_ids=(instrument_id,),
        ),
        plan=LockedExecutionPlan(
            strategy=strategy,
            indicators=(),
            instrument_bands={instrument_id: DriftBand(up=0.10, down=0.20)},
            direction="longonly",
        ),
        component_sources={"strategy.py": "def run(*args, **kwargs):\n    raise AssertionError\n"},
    )


def test_write_wheel_materializes_data_manifest_and_constant_loader(tmp_path) -> None:
    artifact = _artifact()

    wheel_path = write_wheel(artifact, tmp_path)

    with zipfile.ZipFile(wheel_path) as zf:
        names = set(zf.namelist())
        loader = zf.read("aegis_exec_tests_strategy_01234567/__init__.py").decode()
        manifest = json.loads(
            zf.read("aegis_exec_tests_strategy_01234567/bundle_manifest.json")
        )

    assert "aegis_exec_tests_strategy_01234567/strategy.py" in names
    assert "aegis_exec_tests_strategy_01234567/bundle_manifest.json" in names
    assert "aegis_exec_tests_strategy_01234567/__init__.py" in names
    assert "load_installed_bundle(__package__)" in loader
    assert "CONTRACT =" not in loader
    assert "PLAN =" not in loader
    assert manifest["schema_version"] == BUNDLE_PAYLOAD_SCHEMA_VERSION
    assert manifest["contract"]["instrument_ids"] == ["AAPL.NASDAQ"]
    assert manifest["contract"]["missing_index"] == "drop"
    assert manifest["plan"]["instrument_bands"] == {
        "AAPL.NASDAQ": {"up": 0.10, "down": 0.20, "destination_fraction": 1.0}
    }

    sys.path.insert(0, str(wheel_path))
    try:
        module = __import__(artifact.package_name)
        bundle = module.get_bundle()
    finally:
        sys.path.remove(str(wheel_path))
        sys.modules.pop(artifact.package_name, None)

    assert bundle.manifest.candidate_key == "0123456789abcdef"


def test_write_wheel_requires_the_first_v4_capable_runtime(tmp_path) -> None:
    # Schema rejection is the safety mechanism; the package bound makes
    # installation resolve a v4-capable aegis-runtime up front.
    artifact = _artifact()

    wheel_path = write_wheel(artifact, tmp_path)

    with zipfile.ZipFile(wheel_path) as zf:
        metadata_path = next(
            name for name in zf.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = zf.read(metadata_path).decode()

    assert "Requires-Dist: aegis-runtime>=0.3.0" in metadata


def test_write_wheel_uses_same_name_when_same_candidate_already_exists(tmp_path) -> None:
    artifact = _artifact()

    first_path = write_wheel(artifact, tmp_path)
    second_path = write_wheel(artifact, tmp_path)

    assert first_path == second_path
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    assert wheels[0].name == "aegis_exec_tests_strategy_01234567-1.2.3-py3-none-any.whl"


def test_write_wheel_fails_closed_when_package_name_collides_with_different_candidate(
    tmp_path,
) -> None:
    first = _artifact(candidate_key="0123456700000000")
    second = _artifact(candidate_key="01234567ffffffff")

    write_wheel(first, tmp_path)

    with pytest.raises(BundleNameCollisionError, match="01234567"):
        write_wheel(second, tmp_path)

    wheel_path = tmp_path / "aegis_exec_tests_strategy_01234567-1.2.3-py3-none-any.whl"
    with zipfile.ZipFile(wheel_path) as zf:
        manifest = json.loads(
            zf.read("aegis_exec_tests_strategy_01234567/bundle_manifest.json")
        )
    assert manifest["manifest"]["candidate_key"] == "0123456700000000"


def test_write_wheel_checks_later_collision_after_same_candidate_match(tmp_path) -> None:
    same_candidate = _artifact(candidate_key="0123456700000000", version="1.0.0")
    colliding_candidate = _artifact(candidate_key="01234567ffffffff", version="2.0.0")
    staging_dir = tmp_path / "staging"

    write_wheel(same_candidate, tmp_path)
    staged_collision = write_wheel(colliding_candidate, staging_dir)
    (tmp_path / staged_collision.name).write_bytes(staged_collision.read_bytes())

    with pytest.raises(BundleNameCollisionError, match="01234567ffffffff"):
        write_wheel(same_candidate, tmp_path)


def test_write_wheel_fails_visible_when_existing_wheel_is_unreadable(tmp_path) -> None:
    (tmp_path / "broken.whl").write_bytes(b"not a wheel")

    with pytest.raises(BundleManifestReadError, match="could not inspect existing wheel"):
        write_wheel(_artifact(), tmp_path)
