"""Tests for the SideStore source generator (.github/scripts/make_source.py)."""

import json
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / ".github" / "scripts" / "make_source.py"


def _run(tmp_path: Path, **overrides: str) -> subprocess.CompletedProcess[str]:
    args = {
        "repo": "example-owner/example-repo",
        "tag": "app-v0.1.0-7",
        "version": "0.1.0",
        "build": "7",
        "bundle-id": "example.test.app",
        "size": "1234",
        "date": "2000-01-01T00:00:00Z",
        "out": str(tmp_path / "source.json"),
    }
    args.update(overrides)
    cmd = [sys.executable, "-I", str(SCRIPT)]
    for key, value in args.items():
        cmd += [f"--{key}", value]
    return subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603 (fixed local script, test input)


def test_source_has_required_fields(tmp_path: Path) -> None:
    result = _run(tmp_path)
    assert result.returncode == 0, result.stderr
    source = json.loads((tmp_path / "source.json").read_text(encoding="utf-8"))
    app = source["apps"][0]
    version = app["versions"][0]
    assert app["bundleIdentifier"] == "example.test.app"
    assert version["version"] == "0.1.0"
    assert version["buildVersion"] == "7"
    assert version["size"] == 1234
    assert version["downloadURL"].endswith("/releases/download/app-v0.1.0-7/VANTA.ipa")
    assert source["sourceURL"].endswith("/releases/latest/download/source.json")


def test_missing_argument_is_rejected(tmp_path: Path) -> None:
    cmd = [sys.executable, "-I", str(SCRIPT), "--repo", "x/y"]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)  # noqa: S603 (fixed local script, test input)
    assert result.returncode != 0
    assert not (tmp_path / "source.json").exists()


def test_non_numeric_size_is_rejected(tmp_path: Path) -> None:
    assert _run(tmp_path, size="abc").returncode != 0
