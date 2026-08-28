from __future__ import annotations

import json
import os
import re
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


def test_oracle_rom_manifest_pins_external_breakout_rom():
    manifest = json.loads(
        (REPO_ROOT / "validation/oracle-roms.json").read_text(encoding="utf-8")
    )

    assert manifest == {
        "schema": 1,
        "roms": {
            "Breakout-Atari2600-v0": {
                "object_key": "atari2600/Breakout-Atari2600-v0/rom.a26",
                "sha256": (
                    "376323f051c3c373c887fd83abead39d"
                    "87d844ff283d435f4addbfc1710c6fd5"
                ),
                "size": 2048,
            }
        },
    }


def test_operational_pin_selects_stable_retro_turbo_vector_provider():
    pin = json.loads(
        (REPO_ROOT / "validation/stable-retro-turbo.json").read_text(encoding="utf-8")
    )

    assert pin == {
        "distribution": "env-stableretro-turbo",
        "module": "env_stableretro_turbo",
        "repository": "https://github.com/tsilva/env-StableRetro-turbo",
        "revision": "c443cf56003f881042312653a92b17220d1c8459",
        "tree": "668104110e5a471e9766b83210ffb8fee40e5139",
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


def test_make_exposes_one_certifying_turbo_oracle_command():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert makefile.count("\ntest-semantic-oracle:") == 1
    certifying_target = makefile.split("\ntest-semantic-oracle:", 1)[1].split(
        "\n\ntest-semantic-oracle-diagnostic:", 1
    )[0]
    assert "scripts/oracle_release_gate.py generate" in certifying_target
    assert "scripts/oracle_release_gate.py verify-local" in certifying_target
    assert "--prepare-provider \"$$provider_source\"" in makefile
    assert "uv pip install --no-config" in certifying_target
    assert "--default-index https://pypi.org/simple" in certifying_target
    assert '--python "$$candidate_python" "$$provider_wheel"' in certifying_target
    assert 'uv build --no-config --wheel --no-build-logs' in certifying_target
    assert '"$$provider_build"' in certifying_target
    assert "download-published" in certifying_target
    assert "PYTEST_ARGS" not in certifying_target
    assert "ORACLE_RECEIPT" in certifying_target
    assert "ORACLE_CANDIDATE" in certifying_target
    assert "test-semantic-oracle-diagnostic:" in makefile
    assert "NON-CERTIFYING" in makefile
    assert "stable-retro@" not in makefile
    assert "TURBOBENCH" not in makefile
    assert "\ntest-stable-retro:" not in makefile
    assert "\nverify-semantic-oracle:" not in makefile


def test_canonical_macos_builds_scope_provider_and_candidate_targets():
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    certifying_target = makefile.split("\ntest-semantic-oracle:", 1)[1].split(
        "\n\ntest-semantic-oracle-diagnostic:", 1
    )[0]

    provider_build = re.search(
        r"MACOSX_DEPLOYMENT_TARGET=14\.0.*?uv build.*?\$\$provider_build",
        certifying_target,
        flags=re.DOTALL,
    )
    candidate_build = re.search(
        r"MACOSX_DEPLOYMENT_TARGET=11\.0.*?maturin build --release --locked",
        certifying_target,
        flags=re.DOTALL,
    )

    assert provider_build is not None
    assert candidate_build is not None
    assert provider_build.start() < candidate_build.start()
    assert "export MACOSX_DEPLOYMENT_TARGET" not in certifying_target


def test_canonical_macos_candidate_requires_supported_wheel_tag(monkeypatch):
    import oracle_release_gate as gate

    monkeypatch.setattr(gate.sys, "platform", "darwin")
    monkeypatch.setattr(gate.platform, "machine", lambda: "arm64")

    assert gate._candidate_wheel_filename("1.2.3") == (
        "env_breakoutatari2600_turbo_native-1.2.3-"
        "cp311-abi3-macosx_11_0_arm64.whl"
    )


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
                "tree": subprocess.run(
                    ["git", "-C", str(provider_repo), "rev-parse", "HEAD^{tree}"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip(),
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
            f"ORACLE_RECEIPT={tmp_path / 'receipt.json'}",
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
    wheel = tmp_path / "fixture-provider.whl"
    wheel.write_bytes(b"pinned wheel")

    pin = comparison.ProviderPin(
        distribution="fixture-provider",
        module="fixture_provider",
        repository="https://example.invalid/fixture-provider",
        revision="a" * 40,
        tree="b" * 40,
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
            return json.dumps({"url": wheel.as_uri()})

        def locate_file(self, path: str) -> Path:
            return installed_root / path

    monkeypatch.setattr(comparison.importlib, "import_module", lambda _: provider)
    monkeypatch.setattr(
        comparison.importlib.metadata, "distribution", lambda _: _Distribution()
    )
    monkeypatch.setattr(
        comparison, "verify_installed_distribution", lambda _distribution: None
    )
    monkeypatch.setattr(
        comparison, "verify_provider_source_binding", lambda *_arguments: None
    )

    with pytest.raises(
        comparison.PreflightError, match="not imported from the installed distribution"
    ):
        comparison._load_provider(inputs)


def test_provider_source_binding_rejects_substituted_installed_code(tmp_path):
    import compare_stable_retro_turbo as comparison

    provider_repo = tmp_path / "provider"
    source = provider_repo / "fixture_provider/__init__.py"
    source.parent.mkdir(parents=True)
    source.write_text("PINNED = True\n", encoding="utf-8")
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
            "provider",
        ],
        check=True,
    )
    revision = subprocess.run(
        ["git", "-C", str(provider_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    installed_root = tmp_path / "site-packages"
    installed_module = installed_root / "fixture_provider"
    installed_module.mkdir(parents=True)
    module_path = installed_module / "__init__.py"
    module_path.write_text("PINNED = False\n", encoding="utf-8")
    distribution = SimpleNamespace(
        locate_file=lambda path: installed_root / path,
    )
    inputs = comparison.OracleInputs(
        pin=SimpleNamespace(revision=revision, module="fixture_provider"),
        provider_repo=provider_repo,
        data_dir=tmp_path / "data",
        provider_data_dir=tmp_path / "provider-data",
    )

    with pytest.raises(comparison.PreflightError, match="source content does not match"):
        comparison.verify_provider_source_binding(inputs, distribution)


def test_certifying_provider_rejects_dirty_or_attached_checkout(tmp_path):
    import compare_stable_retro_turbo as comparison

    provider_repo = tmp_path / "provider"
    provider_repo.mkdir()
    (provider_repo / "provider.py").write_text("PINNED = True\n", encoding="utf-8")
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
            "provider",
        ],
        check=True,
    )
    revision = subprocess.run(
        ["git", "-C", str(provider_repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    tree = subprocess.run(
        ["git", "-C", str(provider_repo), "rev-parse", "HEAD^{tree}"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    pin = SimpleNamespace(revision=revision, tree=tree)

    with pytest.raises(comparison.PreflightError, match="detached isolated checkout"):
        comparison.require_certifying_provider_checkout(provider_repo, pin)

    subprocess.run(
        ["git", "-C", str(provider_repo), "checkout", "--detach", "-q"], check=True
    )
    (provider_repo / "provider.py").write_text("PINNED = False\n", encoding="utf-8")
    with pytest.raises(comparison.PreflightError, match="provider checkout is dirty"):
        comparison.require_certifying_provider_checkout(provider_repo, pin)


def test_installed_distribution_content_ledger_rejects_mutation(tmp_path):
    import base64
    import hashlib

    import compare_stable_retro_turbo as comparison

    installed = tmp_path / "provider.py"
    installed.write_bytes(b"pinned provider\n")
    digest = base64.urlsafe_b64encode(hashlib.sha256(installed.read_bytes()).digest())
    recorded = SimpleNamespace(mode="sha256", value=digest.rstrip(b"=").decode())
    entry = SimpleNamespace(hash=recorded)
    distribution = SimpleNamespace(
        files=[entry], locate_file=lambda _entry: installed
    )

    assert len(comparison.verify_installed_distribution(distribution)) == 64
    installed.write_bytes(b"substituted provider\n")
    with pytest.raises(comparison.PreflightError, match="distribution file changed"):
        comparison.verify_installed_distribution(distribution)

def test_live_suite_exercises_one_lane_and_multiple_lanes(tmp_path, monkeypatch):
    import compare_stable_retro_turbo as comparison

    provider = SimpleNamespace(
        __version__="1.2.3",
        RetroVecEnv=SimpleNamespace(metadata={"turbo_api_version": 2}),
    )
    inputs = SimpleNamespace(
        pin=SimpleNamespace(
            distribution="fixture-provider",
            module="fixture_provider",
            revision="a" * 40,
            tree="b" * 40,
        ),
        provider_data_dir=tmp_path / "provider-data",
    )
    environment_calls: list[tuple[int, int]] = []

    class _Environment:
        def __init__(self, lane_count: int) -> None:
            self.num_envs = lane_count

        def close(self) -> None:
            pass

    def make_environments(
        inputs, provider, info_path, *, noop_reset_max: int, lane_count: int
    ):
        environment_calls.append((lane_count, noop_reset_max))
        return _Environment(lane_count), _Environment(lane_count)

    monkeypatch.setattr(
        comparison,
        "_load_provider",
        lambda _: comparison.ProviderRuntime(provider, "c" * 64, "d" * 64),
    )
    monkeypatch.setattr(
        comparison,
        "_oracle_info_file",
        lambda provider_data_dir, directory: directory / "oracle-info.json",
    )
    monkeypatch.setattr(comparison, "_make_environments", make_environments)
    monkeypatch.setattr(comparison, "_compare_reset", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        comparison,
        "_trajectory",
        lambda oracle, native, **kwargs: {
            "exact": True,
            "lane_count": oracle.num_envs,
        },
    )
    monkeypatch.setattr(
        comparison,
        "sample_noop_reset_distribution",
        lambda environment, **kwargs: (
            np.ones((32, environment.num_envs), dtype=np.int64),
            {},
        ),
    )
    monkeypatch.setattr(
        comparison,
        "validate_noop_reset_distribution",
        lambda oracle_counts, native_counts, **kwargs: {
            "matches": True,
            "lane_count": oracle_counts.shape[1],
        },
    )
    monkeypatch.setattr(
        comparison,
        "validate_seeded_reset_semantics",
        lambda *args, **kwargs: np.arange(1, 31, dtype=np.int64),
    )

    report = comparison.run_live_suite(inputs, steps=1)

    assert environment_calls == [(1, 0), (1, 30), (2, 0), (2, 30)]
    assert list(report["workloads"]) == ["one-lane", "multi-lane"]
    assert report["workloads"]["one-lane"]["lane_count"] == 1
    assert report["workloads"]["multi-lane"]["lane_count"] == 2


def test_trajectory_resets_terminal_lane_and_completes_fixed_steps(monkeypatch):
    import compare_stable_retro_turbo as comparison

    environment = SimpleNamespace(num_envs=1)
    reset_calls: list[dict | None] = []
    step_calls = 0

    def compare_reset(*_args, options=None, **_kwargs):
        reset_calls.append(options)
        return {"ball_y": np.asarray([1], dtype=np.int64)}

    def compare_step(*_args, **_kwargs):
        nonlocal step_calls
        step_calls += 1
        terminated = np.asarray([step_calls == 1])
        return (
            np.zeros((1, 1), dtype=np.uint8),
            np.zeros(1),
            terminated,
            np.asarray([False]),
            {"ball_y": np.asarray([1], dtype=np.int64)},
        )

    monkeypatch.setattr(comparison, "_compare_reset", compare_reset)
    monkeypatch.setattr(comparison, "_compare_step", compare_step)

    report = comparison._trajectory(
        environment,
        environment,
        name="fixed",
        steps=3,
        random_actions=False,
    )

    assert step_calls == 3
    assert reset_calls[0] is None
    assert len(reset_calls) == 2
    assert np.array_equal(reset_calls[1]["reset_mask"], np.asarray([True]))
    assert report == {
        "exact": True,
        "complete": True,
        "completion": "step-limit",
        "steps": 3,
        "maximum_steps": 3,
        "completed_episodes": [1],
    }


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
