from __future__ import annotations

import base64
import csv
import hashlib
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

from aegis_runtime.execution.bundle_loader import dump_bundle_payload

from research.aegis_research.execution_bundle import BundleArtifact

ENTRY_POINT_GROUP = "aegis.execution_bundles"

LOADER_SOURCE = dedent(
    """
    from aegis_runtime import ExecutionBundle, MarketDataBundle
    from aegis_runtime.execution.bundle_loader import load_installed_bundle

    def get_bundle():
        return load_installed_bundle(__package__)

    bundle = get_bundle()
    __all__ = ['ExecutionBundle', 'MarketDataBundle', 'bundle', 'get_bundle']
    """
).lstrip()


class BundleNameCollisionError(ValueError):
    """Raised when a deterministic package name is already owned by another Candidate."""


class BundleManifestReadError(ValueError):
    """Raised when an existing wheel cannot be inspected for bundle ownership."""


@dataclass(frozen=True)
class BundleOwner:
    package_name: str
    candidate_key: str
    wheel_path: Path


def write_wheel(artifact: BundleArtifact, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    _raise_on_name_collision(artifact, out_dir)
    wheel_path = out_dir / artifact.wheel_filename
    with TemporaryDirectory(prefix="aegis-export-") as tmp:
        root = Path(tmp)
        package_dir = root / artifact.package_name
        package_dir.mkdir()
        _write_package(artifact, package_dir)
        dist_info = root / f"{_wheel_safe(artifact.dist_name)}-{artifact.version}.dist-info"
        dist_info.mkdir()
        _write_dist_info(
            dist_info,
            dist_name=artifact.dist_name,
            version=artifact.version,
            entry_point_name=artifact.wheel_filename,
            entry_point_value=f"{artifact.package_name}:get_bundle",
        )
        _write_wheel_archive(root, wheel_path)
    return wheel_path


def _write_package(artifact: BundleArtifact, package_dir: Path) -> None:
    for filename, source in sorted(artifact.component_sources.items()):
        (package_dir / filename).write_text(source, encoding="utf-8")
    (package_dir / "__init__.py").write_text(LOADER_SOURCE, encoding="utf-8")
    payload = dump_bundle_payload(
        contract=artifact.contract,
        manifest=artifact.manifest,
        plan=artifact.plan,
    )
    (package_dir / "bundle_manifest.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _raise_on_name_collision(artifact: BundleArtifact, out_dir: Path) -> None:
    for wheel_path in sorted(out_dir.glob("*.whl")):
        owner = _bundle_owner(wheel_path)
        if owner is None or owner.package_name != artifact.package_name:
            continue
        if owner.candidate_key == artifact.candidate_key:
            continue
        raise BundleNameCollisionError(
            "Execution Bundle package "
            f"{artifact.package_name!r} is already owned by candidate "
            f"{owner.candidate_key!r} in {owner.wheel_path}; refusing to write "
            f"different candidate {artifact.candidate_key!r}"
        )


def _bundle_owner(wheel_path: Path) -> BundleOwner | None:
    try:
        with zipfile.ZipFile(wheel_path) as zf:
            names = zf.namelist()
            manifest_path = next(
                (name for name in names if name.endswith("bundle_manifest.json")),
                None,
            )
            if manifest_path is None:
                return None
            package_name = manifest_path.split("/")[0]
            manifest = json.loads(zf.read(manifest_path))
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError) as error:
        raise BundleManifestReadError(
            f"could not inspect existing wheel {wheel_path} for bundle ownership"
        ) from error
    candidate_key = manifest.get("manifest", {}).get("candidate_key")
    if not isinstance(candidate_key, str):
        return None
    return BundleOwner(
        package_name=package_name,
        candidate_key=candidate_key,
        wheel_path=wheel_path,
    )


def _write_dist_info(
    dist_info: Path,
    *,
    dist_name: str,
    version: str,
    entry_point_name: str,
    entry_point_value: str,
) -> None:
    (dist_info / "METADATA").write_text(
        "Metadata-Version: 2.1\n"
        f"Name: {dist_name}\n"
        f"Version: {version}\n"
        "Summary: Aegis locked execution bundle\n"
        # The first aegis-runtime that speaks execution_bundle.v5; schema
        # rejection stays the safety mechanism, this just resolves it earlier.
        "Requires-Dist: aegis-runtime>=0.3.0\n",
        encoding="utf-8",
    )
    wheel_metadata = "\n".join(
        [
            "Wheel-Version: 1.0",
            "Generator: aegis-rd-export",
            "Root-Is-Purelib: true",
            "Tag: py3-none-any",
        ]
    )
    (dist_info / "WHEEL").write_text(f"{wheel_metadata}\n", encoding="utf-8")
    (dist_info / "entry_points.txt").write_text(
        f"[{ENTRY_POINT_GROUP}]\n{entry_point_name} = {entry_point_value}\n",
        encoding="utf-8",
    )


def _write_wheel_archive(root: Path, wheel_path: Path) -> None:
    rows: list[tuple[str, str, str]] = []
    files = sorted(path for path in root.rglob("*") if path.is_file() and path.name != "RECORD")
    record_path = next(path for path in root.rglob("*.dist-info") if path.is_dir()) / "RECORD"
    for file_path in files:
        relative = file_path.relative_to(root).as_posix()
        data = file_path.read_bytes()
        rows.append(
            (relative, f"sha256={_urlsafe_b64(hashlib.sha256(data).digest())}", str(len(data)))
        )
    rows.append((record_path.relative_to(root).as_posix(), "", ""))
    with record_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerows(rows)
    with zipfile.ZipFile(wheel_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(path for path in root.rglob("*") if path.is_file()):
            zf.write(file_path, file_path.relative_to(root).as_posix())


def _wheel_safe(value: str) -> str:
    return value.replace("-", "_")


def _urlsafe_b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")
