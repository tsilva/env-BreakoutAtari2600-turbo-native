from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from scripts.benchmark_comparison import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPLIANCE_MATRIX = REPO_ROOT / "docs" / "specification-compliance.md"
ADVERSARIAL_FIXTURE_PATH = Path(__file__).resolve()
FORMER_IDENTIFIERS = (
    "breakout-turbo-env",
    "breakout_turbo_env",
    "Breakout-Turbo-v0",
    "BreakoutTurbo-v0",
    "_breakout_turbo",
    "Breakout Turbo",
)
_BENIGN_AUTHORITY_CONTEXT = re.compile(
    r"(?:\bremov(?:e|ed|ing)\b|\bdeprecat(?:e|ed|ing)\b|"
    r"\bprevent(?:s|ed|ing)?\b|\bprohibit(?:s|ed|ing)?\b|"
    r"\bforbid(?:s|den|ding)?\b|\breject(?:s|ed|ing)?\b|"
    r"\bmust\s+not\b|\bcannot\b|\bnever\b|\bno\s+longer\b|"
    r"\bupstream\s+provenance\b|\blegal\s+context\b|"
    r"\bnot\s+sponsored\b|\bnot\s+in\b|\bassert\s+not\b|"
    r"\bdo\s+not\s+import\b|\bno\b.{0,160}\bis\s+included\b)",
    re.IGNORECASE,
)
_BENIGN_DIRECT_AUTHORITY = re.compile(
    r"(?:\bremov(?:e|ed|ing)\b|\bdeprecat(?:e|ed|ing)\b|"
    r"\bupstream\s+provenance\b|\blegal\s+context\b|"
    r"\bnot\s+sponsored\b|\bno\b.{0,160}\bis\s+included\b|"
    r"\b(?:must\s+not|cannot|never)\b.{0,120}"
    r"\b(?:authority|authoritative|oracle|provider|release\s+gate)\b)",
    re.IGNORECASE,
)
_BENIGN_TURBO_SECONDARY = re.compile(
    r"(?:\b(?:prevent|prohibit|forbid|reject)(?:s|ed|ing)?\b.{0,160}"
    r"Stable\s+Retro\s+Turbo.{0,120}\bsecondary\b|"
    r"\b(?:must\s+not|cannot|never)\b.{0,160}Stable\s+Retro\s+Turbo"
    r".{0,120}\bsecondary\b|Stable\s+Retro\s+Turbo.{0,120}"
    r"\b(?:not|never)\b.{0,40}\bsecondary\b)",
    re.IGNORECASE,
)
_DIRECT_STABLE_RETRO_DISTRIBUTION = re.compile(
    r"(?<![\w-])stable-retro(?!-turbo)(?![\w-])", re.IGNORECASE
)
_DIRECT_STABLE_RETRO_IMPORT = re.compile(
    r"\b(?:import\s+retro\b|from\s+retro(?:\.|\s+import\b))", re.IGNORECASE
)
_DIRECT_STABLE_RETRO_AUTHORITY = re.compile(
    r"(?:\b(?:original\s+)?Stable\s+Retro\b(?!\s+Turbo)"
    r".{0,120}\b(?:authoritative|authority|oracle|provider|checkout|repository|"
    r"comparison|release\s+gate|compatibility\s+target)\b|"
    r"\b(?:authoritative|authority|oracle|provider|checkout|repository|"
    r"comparison|release\s+gate|compatibility\s+target)\b.{0,120}"
    r"\b(?:original\s+)?Stable\s+Retro\b(?!\s+Turbo))",
    re.IGNORECASE,
)
_TURBO_SECONDARY = re.compile(
    r"(?:Stable\s+Retro\s+Turbo.{0,120}\bsecondary\b|"
    r"\bsecondary\b.{0,120}Stable\s+Retro\s+Turbo)",
    re.IGNORECASE,
)


def _spec_requirements() -> list[str]:
    return [
        line.removeprefix("- ")
        for line in (REPO_ROOT / "SPECS.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("- ")
    ]


def _matrix_requirements() -> list[str]:
    text = COMPLIANCE_MATRIX.read_text(encoding="utf-8")
    return re.findall(r"^<!-- SPECS:\d+ -->\n> (.+)$", text, flags=re.MULTILINE)


def _tracked_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    return sorted(
        REPO_ROOT / item for item in result.stdout.decode().split("\0") if item
    )


def _read_text(path: Path) -> str | None:
    content = path.read_bytes()
    if b"\0" in content:
        return None
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return None


def _tracked_text_paths() -> list[Path]:
    return [path for path in _tracked_paths() if _read_text(path) is not None]


def _current_authority_text(path: Path, text: str) -> str:
    relative = path.as_posix()
    if relative == "CHANGELOG.md":
        return re.split(r"^## \[", text, maxsplit=1, flags=re.MULTILINE)[0]
    if re.fullmatch(r"docs/benchmarks/v\d[^/]*\.md", relative):
        return ""
    return text


def _prose_statements(text: str) -> list[str]:
    paragraphs = re.split(r"\n\s*\n", text)
    statements: list[str] = []
    for paragraph in paragraphs:
        compact = re.sub(r"\s+", " ", paragraph).strip()
        if compact:
            statements.extend(re.split(r"(?<=[.!?])\s+", compact))
    return statements


def _authority_violations(path: Path, text: str) -> list[str]:
    current = _current_authority_text(path, text)
    violations: list[str] = []

    for line_number, line in enumerate(current.splitlines(), start=1):
        if _BENIGN_AUTHORITY_CONTEXT.search(line):
            continue
        if _DIRECT_STABLE_RETRO_DISTRIBUTION.search(line):
            violations.append(f"line {line_number}: direct stable-retro distribution")
        if _DIRECT_STABLE_RETRO_IMPORT.search(line):
            violations.append(f"line {line_number}: direct import retro")

    authority_statements = (
        _prose_statements(current)
        if path.suffix.lower() == ".md"
        else current.splitlines()
    )
    for statement in authority_statements:
        if _DIRECT_STABLE_RETRO_AUTHORITY.search(
            statement
        ) and not _BENIGN_DIRECT_AUTHORITY.search(statement):
            violations.append("direct original Stable Retro authority")
        if _TURBO_SECONDARY.search(statement) and not _BENIGN_TURBO_SECONDARY.search(
            statement
        ):
            violations.append("Stable Retro Turbo described as secondary")

    return violations


def _former_identity_violations(path: Path, text: str) -> list[str]:
    current = _current_authority_text(path, text)
    violations: list[str] = []
    historical = re.compile(
        r"\b(?:removed?|renamed?|deprecated|purged|historical|formerly)\b|"
        r"\bformer\s+(?:name|identifier)\b|\b(?:legal|upstream)\s+provenance\b",
        re.I,
    )
    restoration = re.compile(
        r"\b(?:restore|reintroduce|register|publish|current|use\s+.+\s+as)\b", re.I
    )

    for line_number, line in enumerate(current.splitlines(), start=1):
        for identifier in FORMER_IDENTIFIERS:
            if identifier not in line:
                continue
            if historical.search(line) and not restoration.search(line):
                continue
            violations.append(f"line {line_number}: {identifier}")

    return violations


def test_compliance_matrix_maps_every_spec_requirement_literally_and_in_order():
    requirements = _spec_requirements()

    assert len(requirements) == 33
    assert _matrix_requirements() == requirements


@pytest.mark.parametrize("name", ["guard.sh", "Cargo.lock", "release-tool"])
def test_tracked_text_detection_is_content_based(name, tmp_path):
    path = tmp_path / name
    path.write_text("import retro\n", encoding="utf-8")

    assert _read_text(path) == "import retro\n"


def test_tracked_text_detection_rejects_binary_content(tmp_path):
    path = tmp_path / "extensionless"
    path.write_bytes(b"text prefix\x00binary payload")

    assert _read_text(path) is None


def test_tracked_text_enumeration_has_no_suffix_or_executable_name_allowlist(
    tmp_path, monkeypatch
):
    text_paths = [tmp_path / name for name in ("guard.sh", "Cargo.lock", "release-tool")]
    for path in text_paths:
        path.write_text("current contract\n", encoding="utf-8")
    binary = tmp_path / "generated-image"
    binary.write_bytes(b"image\x00payload")
    monkeypatch.setattr(
        sys.modules[__name__], "_tracked_paths", lambda: [*text_paths, binary]
    )

    assert _tracked_text_paths() == text_paths


@pytest.mark.parametrize(
    ("path", "text"),
    [
        (Path("README.md"), "Original Stable Retro is the authoritative oracle."),
        (Path("release.sh"), "pip install stable-retro"),
        (Path("release-tool"), "import retro"),
        (
            Path("CHANGELOG.md"),
            "# Changelog\n\n## Unreleased\n\nStable Retro Turbo is secondary.",
        ),
        (
            Path("docs/specification-compliance.md"),
            "Stable Retro Turbo remains a secondary parity target.",
        ),
    ],
)
def test_authority_guard_rejects_adversarial_current_authority(path, text):
    assert _authority_violations(path, text)


@pytest.mark.parametrize(
    ("path", "text"),
    [
        (
            Path("CHANGELOG.md"),
            "## [0.5.3] - 2026-08-12\n\nStable Retro Turbo was secondary.",
        ),
        (
            Path("CHANGELOG.md"),
            "## Unreleased\n\nRemoved the original Stable Retro authority path.",
        ),
        (
            Path("THIRD_PARTY_NOTICES.md"),
            "The project is not sponsored by the maintainers of Stable Retro.",
        ),
        (
            Path("CONTRIBUTING.md"),
            "Original Stable Retro may appear only as upstream provenance, never as an oracle.",
        ),
        (Path("Makefile"), 'assert "stable-retro@" not in makefile'),
        (Path("provider.py"), "import env_stableretro_turbo as retro"),
        (
            Path("docs/policy.md"),
            "Prevent Stable Retro Turbo from being described as secondary.",
        ),
    ],
)
def test_authority_guard_allows_negation_provenance_and_versioned_history(path, text):
    assert not _authority_violations(path, text)


@pytest.mark.parametrize(
    "identifier",
    [
        "breakout-turbo-env",
        "breakout_turbo_env",
        "Breakout-Turbo-v0",
        "BreakoutTurbo-v0",
        "_breakout_turbo",
        "Breakout Turbo",
    ],
)
def test_former_identity_guard_rejects_each_known_identifier(identifier):
    text = f"Register {identifier} as the current public command or environment ID."

    assert _former_identity_violations(Path("README.md"), text)


def test_former_identity_guard_allows_narrow_historical_mentions():
    assert not _former_identity_violations(
        Path("CHANGELOG.md"),
        "## Unreleased\n\nRemoved the legacy `BreakoutTurbo-v0` registration.",
    )
    assert not _former_identity_violations(
        Path("CHANGELOG.md"),
        "## [0.5.0] - 2026-07-27\n\nThe old command was `breakout-turbo-env`.",
    )
    assert not _former_identity_violations(
        Path("THIRD_PARTY_NOTICES.md"),
        "The former name `Breakout Turbo` appears only as legal provenance.",
    )


def test_documented_pytest_selectors_collect_and_release_commands_parse():
    matrix = COMPLIANCE_MATRIX.read_text(encoding="utf-8")
    assert not re.findall(r"`test_[^`]+`", matrix)
    selectors = sorted(set(re.findall(r"`(tests/test_[^`]+)`", matrix)))
    assert selectors

    subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *selectors],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )

    rust_selectors = re.findall(r"`(parity_tests::[a-z0-9_]+)`", matrix)
    rust_source = (REPO_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
    assert rust_selectors
    for selector in rust_selectors:
        assert f"fn {selector.removeprefix('parity_tests::')}(" in rust_source

    release_helper = ".codex/skills/build-release/scripts/release_build.py"
    assert (
        f".venv/bin/python {release_helper} build-platform --platform macos-arm64"
        in matrix
    )
    assert f".venv/bin/python {release_helper} build-sdist" in matrix
    for command in ("build-platform", "build-sdist"):
        result = subprocess.run(
            [sys.executable, release_helper, command, "--help"],
            cwd=REPO_ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        assert "usage:" in result.stdout


def test_policy_and_render_paths_share_the_native_indexed_pixel_source():
    source = (REPO_ROOT / "src" / "lib.rs").read_text(encoding="utf-8")
    render_path = source.split("fn render_indexed", 1)[1].split("fn palette_gray", 1)[0]
    policy_path = source.split("fn policy_gray_pixel", 1)[1].split(
        "fn resized_pixel", 1
    )[0]

    assert "indexed_pixel(visual" in render_path
    assert "indexed_pixel(visual" in policy_path


def test_current_public_contract_never_demotes_the_turbo_oracle():
    violations: list[str] = []
    for path in _tracked_text_paths():
        if path.resolve() == ADVERSARIAL_FIXTURE_PATH:
            continue
        text = _read_text(path)
        assert text is not None
        violations.extend(
            f"{path.relative_to(REPO_ROOT)}: {finding}"
            for finding in _authority_violations(path.relative_to(REPO_ROOT), text)
        )

    assert not violations, "\n".join(violations)


def test_current_project_surfaces_do_not_restore_former_identifiers():
    violations: list[str] = []

    for path in _tracked_text_paths():
        if path.resolve() == ADVERSARIAL_FIXTURE_PATH:
            continue
        text = _read_text(path)
        assert text is not None
        violations.extend(
            f"{path.relative_to(REPO_ROOT)}: {finding}"
            for finding in _former_identity_violations(
                path.relative_to(REPO_ROOT), text
            )
        )

    assert not violations, "\n".join(violations)


def test_distributable_package_tree_contains_no_oracle_payload():
    tracked = [path.relative_to(REPO_ROOT) for path in _tracked_paths()]
    forbidden_suffixes = {".a26", ".bin", ".rom", ".sav", ".state"}
    forbidden_payloads = [
        path
        for path in tracked
        if path.suffix.lower() in forbidden_suffixes
    ]
    package_data = [
        path
        for path in tracked
        if path.parts[:2]
        == ("python", "env_breakoutatari2600_turbo_native")
        and "data" in path.parts
    ]
    metadata = tomllib.loads(
        (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )

    assert not forbidden_payloads
    assert package_data == [
        Path(
            "python/env_breakoutatari2600_turbo_native/"
            "data/Breakout-Atari2600-v0/metadata.json"
        )
    ]
    assert metadata["tool"]["maturin"]["include"] == [
        "python/env_breakoutatari2600_turbo_native/data/**/metadata.json",
        "python/env_breakoutatari2600_turbo_native/py.typed",
    ]


def test_public_docs_use_frame_terms_from_the_domain_glossary():
    rendered_docs = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
    environment_docs = (REPO_ROOT / "docs" / "environment.md").read_text(
        encoding="utf-8"
    )
    benchmarking_docs = (REPO_ROOT / "docs" / "benchmarking.md").read_text(
        encoding="utf-8"
    )
    benchmark_report = (
        REPO_ROOT / "docs" / "benchmarks" / "v0.3.0-macos-arm64.md"
    ).read_text(encoding="utf-8")
    public_api = (
        REPO_ROOT / "python" / "env_breakoutatari2600_turbo_native" / "env.py"
    ).read_text(encoding="utf-8")
    contributing = (REPO_ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
    public_prose = rendered_docs + environment_docs + contributing + public_api

    assert "Opt into raw frames" not in rendered_docs
    assert "raw emulator frames" not in environment_docs
    assert "Stable Retro-compatible" not in rendered_docs + environment_docs
    assert "with ALE, Stable Retro," not in benchmarking_docs
    assert "Stable Retro performs" not in benchmark_report
    assert "native 160×210 Atari Breakout frame" not in rendered_docs
    assert "160×210 native indexed frame" in rendered_docs
    assert "native 160x210 RGB frame" not in public_api
    assert "Stella RGB rendered frame" in public_api
    for ambiguous in (
        r"\bnative rendering\b",
        r"\bnative \d+[x×]\d+ Atari Breakout frame\b",
        r"\bnative \d+[x×]\d+ RGB frame\b",
        r"\b(?:one|four) native frames?\b",
        r"\braw frames?\b",
    ):
        assert not re.search(ambiguous, public_prose, re.IGNORECASE), ambiguous


def test_benchmark_comparison_names_the_turbo_provider_explicitly():
    parser = build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--stable-retro-turbo-repo" in option_strings
    assert "--stable-retro-repo" not in option_strings
