from pathlib import Path

from aegis_runtime import debit_interest, gate

from research.aegis_research import portfolio_callbacks
from research.aegis_research.portfolios import (
    VBT_STATICIZED_CACHE_ENV,
    _band_pre_order_segment_nb,
    _vbt_staticized_cache_dir,
    _vbt_staticized_callback_path,
    _vbt_staticized_source_paths,
)


def test_staticized_cache_dir_uses_explicit_env(tmp_path, monkeypatch) -> None:
    cache_dir = tmp_path / "custom-vbt-cache"
    monkeypatch.setenv(VBT_STATICIZED_CACHE_ENV, str(cache_dir))

    resolved = _vbt_staticized_cache_dir()

    assert resolved == cache_dir
    assert cache_dir.is_dir()


def test_staticized_cache_dir_uses_xdg_cache_home(tmp_path, monkeypatch) -> None:
    xdg_cache = tmp_path / "xdg-cache"
    monkeypatch.delenv(VBT_STATICIZED_CACHE_ENV, raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(xdg_cache))

    resolved = _vbt_staticized_cache_dir()

    assert resolved.parent == xdg_cache / "aegis-rd" / "vbt-staticization"
    assert resolved.name.startswith("driftband-")
    assert resolved.is_dir()


def test_staticized_callback_module_exports_vbt_symbol() -> None:
    callback_path = _vbt_staticized_callback_path()

    assert callback_path == Path(portfolio_callbacks.__file__)
    assert callback_path.name == "portfolio_callbacks.py"
    assert portfolio_callbacks.pre_order_segment_func_nb is _band_pre_order_segment_nb


def test_staticized_cache_key_tracks_shared_gate_source() -> None:
    source_paths = _vbt_staticized_source_paths()

    assert Path(gate.__code__.co_filename).resolve() in source_paths


def test_staticized_cache_key_tracks_shared_financing_source() -> None:
    source_paths = _vbt_staticized_source_paths()

    assert Path(debit_interest.__code__.co_filename).resolve() in source_paths
