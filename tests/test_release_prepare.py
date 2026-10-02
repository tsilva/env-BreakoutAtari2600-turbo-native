from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
RELEASE_SCRIPT = REPO_ROOT / "scripts" / "release.py"


def release_module():
    spec = importlib.util.spec_from_file_location("release_script", RELEASE_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_prepare_cli_requires_explicit_prepare_command():
    release = release_module()

    args = release.parse_args(["prepare", "--to", "0.3.6"])

    assert args.command == "prepare"
    assert args.to == "0.3.6"


def test_release_script_has_no_commit_tag_push_or_skip_authority():
    source = RELEASE_SCRIPT.read_text(encoding="utf-8")

    for forbidden in (
        '"git", "commit"',
        '"git", "tag"',
        '"git", "push"',
        "--skip-checks",
        '"uv", "lock"',
        '"cargo", "generate-lockfile"',
    ):
        assert forbidden not in source

    assert "Review and commit these files directly on main" in source
    assert "pull request" not in source


def test_dependency_snapshot_ignores_only_first_party_version():
    release = release_module()

    before = release.dependency_graph_snapshot()
    assert "env-breakoutatari2600-turbo-native" in before
    assert '"uv_options"' in before


def test_prepare_change_allowlist_contains_only_release_metadata():
    release = release_module()

    assert release.ALLOWED_RELEASE_FILES == {
        "Cargo.lock",
        "Cargo.toml",
        "CITATION.cff",
        "VERSION.txt",
        "pyproject.toml",
        "uv.lock",
    }


def test_changed_paths_does_not_parse_porcelain_status_columns(monkeypatch):
    release = release_module()
    outputs = iter(("CITATION.cff\nVERSION.txt", "", ""))
    monkeypatch.setattr(release, "capture", lambda _command: next(outputs))

    assert release.changed_paths() == ["CITATION.cff", "VERSION.txt"]


def test_prepare_needs_no_native_tools_or_dependency_installation(monkeypatch):
    release = release_module()
    calls = []
    monkeypatch.setattr(release, "ensure_clean", lambda: None)
    monkeypatch.setattr(release, "ensure_synced", lambda: "origin/main")
    monkeypatch.setattr(release, "target_version", lambda _args: "1.2.3")
    monkeypatch.setattr(release, "capture", lambda _args: "")
    monkeypatch.setattr(release, "dependency_graph_snapshot", lambda: "graph")
    monkeypatch.setattr(release, "helper", lambda *args: calls.append(args[0]))
    monkeypatch.setattr(
        release,
        "validate_release_notes",
        lambda version: calls.append("validate-notes"),
    )
    monkeypatch.setattr(
        release, "ensure_only_release_files_changed", lambda: ["VERSION.txt"]
    )
    monkeypatch.setattr(release, "run", lambda args: calls.append(args))
    monkeypatch.setattr(
        release,
        "run_checks",
        lambda: (_ for _ in ()).throw(AssertionError("native checks ran locally")),
    )

    release.prepare(release.parse_args(["prepare"]))

    assert "bump-version" in calls
    assert "check-lock-policy" in calls


def test_resume_does_not_bump_again(monkeypatch):
    release = release_module()
    calls = []
    monkeypatch.setattr(
        release, "ensure_only_release_files_changed", lambda: ["VERSION.txt"]
    )
    monkeypatch.setattr(release, "ensure_prepared_graph_unchanged", lambda: None)
    monkeypatch.setattr(release, "ensure_synced", lambda: "origin/main")
    monkeypatch.setattr(
        release, "read_toml", lambda _path: {"project": {"version": "1.2.3"}}
    )
    monkeypatch.setattr(release, "capture", lambda _args: "")
    monkeypatch.setattr(release, "dependency_graph_snapshot", lambda: "graph")
    monkeypatch.setattr(release, "helper", lambda *args: calls.append(args[0]))
    monkeypatch.setattr(release, "validate_release_notes", lambda version: None)
    monkeypatch.setattr(release, "run", lambda args: None)

    release.prepare(release.parse_args(["prepare", "--resume"]))

    assert "bump-version" not in calls
    assert calls == ["check-pypi", "check-version", "check-lock-policy"]


def test_resume_rejects_changed_dependency_graph(monkeypatch):
    import pytest

    release = release_module()
    monkeypatch.setattr(
        release, "capture", lambda args: '[[package]]\nname="numpy"\nversion="1.0"'
    )
    monkeypatch.setattr(
        release,
        "read_toml",
        lambda path: {"package": [{"name": "numpy", "version": "2.0"}]},
    )

    with pytest.raises(SystemExit, match="third-party dependencies"):
        release.ensure_prepared_graph_unchanged()
