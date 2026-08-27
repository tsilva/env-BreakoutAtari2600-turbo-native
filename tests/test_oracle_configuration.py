from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))


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
    assert "--prepare-provider \"$$provider_source\"" in makefile
    assert 'uv pip install --python "$(PYTHON)" "$$provider_source"' in makefile
    assert 'BREAKOUT_STABLE_RETRO_TURBO_REPO="$$provider_source"' in makefile
    assert "stable-retro@" not in makefile
    assert "TURBOBENCH" not in makefile
    assert "\ntest-stable-retro:" not in makefile
    assert "\nverify-semantic-oracle:" not in makefile


def test_prepare_provider_uses_only_the_pinned_committed_source(tmp_path):
    fixture_root = tmp_path / "fixture-project"
    fixture_script = fixture_root / "scripts/compare_stable_retro_turbo.py"
    fixture_script.parent.mkdir(parents=True)
    shutil.copy2(
        REPO_ROOT / "scripts/compare_stable_retro_turbo.py",
        fixture_script,
    )

    data_dir = tmp_path / "data/stable/Breakout-Atari2600-v0"
    data_dir.mkdir(parents=True)
    (data_dir / "rom.a26").write_bytes(b"external test fixture")
    provider_repo = tmp_path / "provider"
    provider_package = provider_repo / "fixture_provider"
    provider_data = provider_package / "data/stable/Breakout-Atari2600-v0"
    provider_data.mkdir(parents=True)
    (provider_package / "VERSION.txt").write_text("1.2.3\n", encoding="utf-8")
    (provider_package / "marker.txt").write_text("pinned\n", encoding="utf-8")
    (provider_package / "staged-marker.txt").write_text(
        "pinned\n", encoding="utf-8"
    )
    for filename in ("Start.state", "data.json", "scenario.json"):
        (provider_data / filename).write_text("pinned\n", encoding="utf-8")
    (provider_repo / ".gitignore").write_text("ignored-payload\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(provider_repo)], check=True)
    subprocess.run(["git", "-C", str(provider_repo), "add", "."], check=True)
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
            "-qm",
            "pinned provider",
        ],
        check=True,
    )
    revision = subprocess.run(
        ["git", "-C", str(provider_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    pin_dir = fixture_root / "validation"
    pin_dir.mkdir()
    (pin_dir / "stable-retro-turbo.json").write_text(
        json.dumps(
            {
                "distribution": "fixture-provider",
                "module": "fixture_provider",
                "repository": "https://example.invalid/fixture-provider",
                "revision": revision,
                "turbo_api_version": 2,
                "version": "1.2.3",
            }
        ),
        encoding="utf-8",
    )

    (provider_package / "marker.txt").write_text("modified\n", encoding="utf-8")
    (provider_package / "staged-marker.txt").write_text(
        "modified\n", encoding="utf-8"
    )
    subprocess.run(
        ["git", "-C", str(provider_repo), "add", "fixture_provider/staged-marker.txt"],
        check=True,
    )
    (provider_package / "untracked-payload").write_text("attack\n", encoding="utf-8")
    (provider_repo / "ignored-payload").write_text("attack\n", encoding="utf-8")
    prepared_provider = tmp_path / "prepared-provider"

    result = subprocess.run(
        [
            sys.executable,
            str(fixture_script),
            "--provider-repo",
            str(provider_repo),
            "--data-root",
            str(tmp_path / "data"),
            "--prepare-provider",
            str(prepared_provider),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert (prepared_provider / "fixture_provider/marker.txt").read_text(
        encoding="utf-8"
    ) == "pinned\n"
    assert (prepared_provider / "fixture_provider/staged-marker.txt").read_text(
        encoding="utf-8"
    ) == "pinned\n"
    assert not (prepared_provider / "fixture_provider/untracked-payload").exists()
    assert not (prepared_provider / "ignored-payload").exists()
    prepared_revision = subprocess.run(
        ["git", "-C", str(prepared_provider), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    assert prepared_revision == revision


def test_canonical_command_rejects_wrong_checkout_before_install(tmp_path):
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
            "-qm",
            "incompatible provider",
        ],
        check=True,
    )
    install_marker = tmp_path / "install-attempted"
    fake_uv = tmp_path / "uv"
    fake_uv.write_text(
        f"#!/bin/sh\n: > {install_marker}\nexit 91\n",
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)

    result = subprocess.run(
        [
            "make",
            "--silent",
            "test-semantic-oracle",
            f"PYTHON={sys.executable}",
            f"RETRO_DATA_PATH={tmp_path / 'data'}",
            f"STABLE_RETRO_TURBO_REPO={provider_repo}",
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PATH": f"{tmp_path}:{os.environ['PATH']}"},
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "provider revision is incompatible" in result.stderr
    assert not install_marker.exists()


def test_pull_request_template_names_the_sole_turbo_oracle_command():
    template = (REPO_ROOT / ".github/pull_request_template.md").read_text(
        encoding="utf-8"
    )

    assert "Pinned Stable Retro Turbo sole-oracle run" in template
    assert "RETRO_DATA_PATH=/path/to/lawful/stable_retro/data make test-semantic-oracle" in template
    assert "Live Stable Retro parity" not in template


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


def test_provider_load_rejects_shadow_module_despite_pinned_install_provenance(
    tmp_path, monkeypatch
):
    import compare_stable_retro_turbo as comparison

    provider_repo = tmp_path / "pinned-provider"
    installed_root = tmp_path / "site-packages"
    installed_module = installed_root / "fixture_provider"
    shadow_module = tmp_path / "shadow/fixture_provider/__init__.py"
    provider_repo.mkdir()
    installed_module.mkdir(parents=True)
    shadow_module.parent.mkdir(parents=True)
    shadow_module.write_text("shadow code\n", encoding="utf-8")

    pin = comparison.ProviderPin(
        distribution="fixture-provider",
        module="fixture_provider",
        repository="https://example.invalid/fixture-provider",
        revision="a" * 40,
        turbo_api_version=2,
        version="1.2.3",
    )
    inputs = comparison.OracleInputs(
        pin=pin,
        provider_repo=provider_repo,
        data_dir=tmp_path / "data",
        provider_data_dir=tmp_path / "provider-data",
    )
    provider = SimpleNamespace(
        __file__=str(shadow_module),
        __version__="1.2.3",
        RetroVecEnv=SimpleNamespace(
            metadata={"turbo_api_version": 2, "transition_transport": "numpy"}
        ),
    )

    class _Distribution:
        def read_text(self, filename: str) -> str | None:
            assert filename == "direct_url.json"
            return json.dumps({"url": provider_repo.as_uri()})

        def locate_file(self, path: str) -> Path:
            return installed_root / path

    monkeypatch.setattr(comparison.importlib, "import_module", lambda _: provider)
    monkeypatch.setattr(
        comparison.importlib.metadata, "distribution", lambda _: _Distribution()
    )

    with pytest.raises(
        comparison.PreflightError, match="not imported from the installed distribution"
    ):
        comparison._load_provider(inputs)


def test_reset_distribution_comparison_rejects_a_wrong_distribution():
    from compare_stable_retro_turbo import (
        ObservableMismatch,
        validate_noop_reset_distribution,
    )

    oracle_counts = np.concatenate(
        (np.ones(300, dtype=np.int64), np.full(300, 30, dtype=np.int64))
    ).reshape(-1, 1)
    wrong_native_counts = np.concatenate(
        (np.ones(408, dtype=np.int64), np.full(192, 30, dtype=np.int64))
    ).reshape(-1, 1)

    with pytest.raises(ObservableMismatch, match="distribution mismatch"):
        validate_noop_reset_distribution(
            oracle_counts,
            wrong_native_counts,
            maximum=30,
        )


class _ResetCountEnvironment:
    num_envs = 2

    def __init__(
        self,
        *,
        corrupt_lane_one_distribution: bool = False,
        corrupt_semantics_at: int | None = None,
    ) -> None:
        self.corrupt_lane_one_distribution = corrupt_lane_one_distribution
        self.corrupt_semantics_at = corrupt_semantics_at
        self.frames = np.zeros((2, 1, 1, 3), dtype=np.uint8)

    def reset(self, *, seed):
        counts = np.asarray(
            [
                np.random.default_rng(value).integers(1, 31, dtype=np.uint64)
                for value in seed
            ],
            dtype=np.int64,
        )
        if self.corrupt_lane_one_distribution:
            counts[1] = 1
        observation = counts.astype(np.uint8).reshape(2, 1)
        if self.corrupt_semantics_at is not None:
            observation[counts == self.corrupt_semantics_at] += 1
        self.frames = np.zeros((2, 1, 1, 3), dtype=np.uint8)
        info = {
            "ball_y": counts.copy(),
            "lives": np.full(2, 5, dtype=np.int64),
            "score": np.zeros(2, dtype=np.int64),
            "state_index": np.zeros(2, dtype=np.int64),
            "start_source": np.asarray(["Start", "Start"]),
            "noop_reset_count": counts.copy(),
        }
        return observation, info

    def render_lane(self, lane: int) -> np.ndarray:
        return self.frames[lane]


def test_reset_distribution_comparison_samples_every_lane():
    from compare_stable_retro_turbo import (
        ObservableMismatch,
        sample_noop_reset_distribution,
        validate_noop_reset_distribution,
    )

    oracle_counts, _ = sample_noop_reset_distribution(
        _ResetCountEnvironment(),
        seeds=tuple(range(60)),
        maximum=30,
    )
    native_counts, _ = sample_noop_reset_distribution(
        _ResetCountEnvironment(corrupt_lane_one_distribution=True),
        seeds=tuple(range(60)),
        maximum=30,
    )

    assert oracle_counts.shape == (60, 2)
    with pytest.raises(ObservableMismatch, match="distribution mismatch"):
        validate_noop_reset_distribution(
            oracle_counts,
            native_counts,
            maximum=30,
        )


def test_reset_distribution_comparison_rejects_drift_hidden_by_lane_pooling():
    from compare_stable_retro_turbo import (
        ObservableMismatch,
        validate_noop_reset_distribution,
    )

    oracle_counts = np.full((256, 2), 30, dtype=np.int64)
    wrong_native_counts = oracle_counts.copy()
    wrong_native_counts[:47, 1] = 1

    with pytest.raises(
        ObservableMismatch, match=r"lane 1.*distribution mismatch"
    ):
        validate_noop_reset_distribution(
            oracle_counts,
            wrong_native_counts,
            maximum=30,
        )


def test_aligned_reset_semantics_reject_a_wrong_nondefault_count():
    from compare_stable_retro_turbo import (
        ObservableMismatch,
        validate_seeded_reset_semantics,
    )

    seeds_by_count: dict[int, tuple[int, int]] = {}
    for seed in range(100_000):
        count = int(np.random.default_rng(seed).integers(1, 31, dtype=np.uint64))
        seeds_by_count.setdefault(count, (seed, 0))
        if len(seeds_by_count) == 30:
            break

    with pytest.raises(
        ObservableMismatch,
        match="seeded reset noop count 17: policy observation mismatch",
    ):
        validate_seeded_reset_semantics(
            _ResetCountEnvironment(),
            _ResetCountEnvironment(corrupt_semantics_at=17),
            representative_seeds=seeds_by_count,
            maximum=30,
        )
