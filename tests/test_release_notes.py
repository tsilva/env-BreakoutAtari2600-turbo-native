from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "release_notes.py"


def release_notes_module():
    spec = importlib.util.spec_from_file_location("release_notes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


@pytest.fixture
def repository(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.name", "Release test")
    git(tmp_path, "config", "user.email", "release-test@example.invalid")
    git(tmp_path, "commit", "--allow-empty", "-qm", "Initial release")
    git(tmp_path, "tag", "v1.0.0")
    return tmp_path


def test_notes_cover_previous_release_to_exact_commit_without_changelog(repository):
    module = release_notes_module()
    git(repository, "commit", "--allow-empty", "-qm", "Fix selective resets")
    selected = git(repository, "rev-parse", "HEAD")
    git(repository, "commit", "--allow-empty", "-qm", "Later unrelated change")

    notes = module.generate_notes(repository, "1.1.0", ref=selected)

    assert "Fix selective resets" in notes
    assert "Initial release" not in notes
    assert "Later unrelated change" not in notes
    assert not (repository / "CHANGELOG.md").exists()


def test_notes_exclude_target_tag_and_release_commits(repository):
    module = release_notes_module()
    git(repository, "commit", "--allow-empty", "-qm", "Add rendering")
    git(repository, "commit", "--allow-empty", "-qm", "Add rendering")
    git(repository, "commit", "--allow-empty", "-qm", "Release v1.1.0")
    git(repository, "tag", "v1.1.0")

    notes = module.generate_notes(repository, "1.1.0")

    assert notes.count("Add rendering") == 1
    assert "Release v1.1.0" not in notes


def test_notes_support_project_tag_prefix(repository):
    module = release_notes_module()
    git(repository, "tag", "project-v1.0.0")
    git(repository, "commit", "--allow-empty", "-qm", "Fix playback")

    assert "Fix playback" in module.generate_notes(
        repository, "1.1.0", tag_prefix="project-v"
    )


def test_empty_change_range_requires_reviewed_notes(repository):
    module = release_notes_module()

    with pytest.raises(ValueError, match="no releasable commits"):
        module.generate_notes(repository, "1.1.0")


def test_shallow_history_is_rejected(repository, tmp_path_factory):
    module = release_notes_module()
    shallow = tmp_path_factory.mktemp("shallow") / "checkout"
    subprocess.run(
        ["git", "clone", "-q", "--depth=1", repository.as_uri(), str(shallow)],
        check=True,
    )

    with pytest.raises(ValueError, match="full Git history"):
        module.generate_notes(shallow, "1.1.0")


def test_cli_accepts_reviewed_notes_without_changing_repository(repository, capsys):
    module = release_notes_module()
    reviewed = repository / "reviewed.txt"
    reviewed.write_text("### Fixed\n\n- Preserve terminal observations.\n")
    before = git(repository, "status", "--porcelain")

    module.main(["--version", "1.1.0", "--notes-file", str(reviewed)])

    assert "Preserve terminal observations" in capsys.readouterr().out
    assert git(repository, "status", "--porcelain") == before


@pytest.mark.parametrize(
    "notes", ["", "## Fixed\n", "<!-- pending -->\n", "<!--\npending\n-->", "- \n"]
)
def test_reviewed_notes_require_meaningful_content(notes):
    with pytest.raises(ValueError, match="meaningful text"):
        release_notes_module().validate_notes(notes)
