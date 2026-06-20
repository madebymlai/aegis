"""aegis-data CLI (offline commands)."""

from __future__ import annotations

from aegis_data.cli import main


def test_path_prints_store_dir(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    rc = main(["path"])
    assert rc == 0
    assert str(tmp_path) in capsys.readouterr().out


def test_ls_reports_empty_store(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("AEGIS_DATA_DIR", str(tmp_path))
    rc = main(["ls", "--dataset", "GLBX.MDP3"])
    assert rc == 0
    assert "empty" in capsys.readouterr().out
