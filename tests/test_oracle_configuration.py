from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_operational_pin_selects_stable_retro_turbo_vector_provider():
    pin = json.loads(
        (REPO_ROOT / "validation/stable-retro-turbo.json").read_text(encoding="utf-8")
    )

    assert pin == {
        "distribution": "env-stableretro-turbo",
        "module": "env_stableretro_turbo",
        "repository": "https://github.com/tsilva/env-StableRetro-turbo",
        "revision": "c443cf56003f881042312653a92b17220d1c8459",
        "turbo_api_version": 2,
        "version": "1.0.1.post44",
    }


def test_oracle_dependencies_stay_outside_the_distributed_package():
    project = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))[
        "project"
    ]
    dependencies = [*project["dependencies"]]
    for extra in project.get("optional-dependencies", {}).values():
        dependencies.extend(extra)

    normalized = {dependency.lower().replace("_", "-") for dependency in dependencies}
    assert not any("stable-retro" in dependency for dependency in normalized)
    assert not any("stableretro" in dependency for dependency in normalized)


def test_make_exposes_one_required_turbo_oracle_command():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert makefile.count("\ntest-semantic-oracle:") == 1
    assert "BREAKOUT_REQUIRE_STABLE_RETRO_TURBO=1" in makefile
    assert "tests/test_stable_retro_turbo_oracle.py" in makefile
    assert "stable-retro@" not in makefile
    assert "TURBOBENCH" not in makefile
    assert "\ntest-stable-retro:" not in makefile
    assert "\nverify-semantic-oracle:" not in makefile


def test_required_validation_fails_clearly_without_pinned_provider(tmp_path):
    data_dir = tmp_path / "data/stable/Breakout-Atari2600-v0"
    data_dir.mkdir(parents=True)
    (data_dir / "rom.a26").write_bytes(b"external test fixture")
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/compare_stable_retro_turbo.py"),
            "--provider-repo",
            str(tmp_path / "missing-provider"),
            "--data-root",
            str(tmp_path / "data"),
            "--preflight-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "pinned Stable Retro Turbo provider checkout not found" in result.stderr


def test_required_validation_fails_clearly_without_lawful_rom(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/compare_stable_retro_turbo.py"),
            "--provider-repo",
            str(tmp_path / "missing-provider"),
            "--data-root",
            str(tmp_path / "missing-data"),
            "--preflight-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "lawful Breakout oracle data is incomplete" in result.stderr


def test_required_validation_fails_clearly_for_incompatible_provider(tmp_path):
    data_dir = tmp_path / "data/stable/Breakout-Atari2600-v0"
    data_dir.mkdir(parents=True)
    (data_dir / "rom.a26").write_bytes(b"external test fixture")
    provider_repo = tmp_path / "provider"
    (provider_repo / "env_stableretro_turbo").mkdir(parents=True)
    (provider_repo / "env_stableretro_turbo/__init__.py").write_text(
        "__version__ = 'incompatible'\n", encoding="utf-8"
    )
    subprocess.run(["git", "init", "-q", str(provider_repo)], check=True)
    subprocess.run(
        ["git", "-C", str(provider_repo), "add", "env_stableretro_turbo"],
        check=True,
    )
    subprocess.run(
        [
            "git",
            "-C",
            str(provider_repo),
            "-c",
            "user.name=Oracle test",
            "-c",
            "user.email=oracle-test@example.invalid",
            "commit",
            "--allow-empty",
            "-qm",
            "incompatible provider",
        ],
        check=True,
    )

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "scripts/compare_stable_retro_turbo.py"),
            "--provider-repo",
            str(provider_repo),
            "--data-root",
            str(tmp_path / "data"),
            "--preflight-only",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "provider revision is incompatible" in result.stderr
