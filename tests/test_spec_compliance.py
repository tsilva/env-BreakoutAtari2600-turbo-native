from __future__ import annotations

import re
import subprocess
import tomllib
from pathlib import Path

from scripts.benchmark_comparison import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPLIANCE_MATRIX = REPO_ROOT / "docs" / "specification-compliance.md"

TEXT_SUFFIXES = {".json", ".md", ".py", ".rs", ".toml", ".txt", ".yml", ".yaml"}
QUOTED_HISTORICAL_OR_LEGAL_SURFACES = (
    REPO_ROOT / "CHANGELOG.md",
    REPO_ROOT / "CONTEXT.md",
    REPO_ROOT / "SPECS.md",
    REPO_ROOT / "THIRD_PARTY_NOTICES.md",
    COMPLIANCE_MATRIX,
    REPO_ROOT / "docs" / "benchmarks" / "v0.3.0-macos-arm64.md",
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
    return [REPO_ROOT / item for item in result.stdout.decode().split("\0") if item]


def _tracked_text_paths() -> list[Path]:
    return [
        path
        for path in _tracked_paths()
        if path.name == "Makefile" or path.suffix in TEXT_SUFFIXES
    ]


def test_compliance_matrix_maps_every_spec_requirement_literally_and_in_order():
    requirements = _spec_requirements()

    assert len(requirements) == 33
    assert _matrix_requirements() == requirements


def test_current_public_contract_never_demotes_the_turbo_oracle():
    forbidden = {
        "original Stable Retro": re.compile(r"original\s+Stable\s+Retro", re.I),
        "Turbo described as secondary": re.compile(
            r"(?:Stable\s+Retro\s+Turbo.{0,120}secondary|"
            r"secondary.{0,120}Stable\s+Retro\s+Turbo)",
            re.I | re.S,
        ),
        "unqualified Stable Retro checkout": re.compile(
            r"Stable\s+Retro\s+(?:checkout|repository|provider|oracle)", re.I
        ),
    }

    violations: list[str] = []
    for path in _tracked_text_paths():
        if path in QUOTED_HISTORICAL_OR_LEGAL_SURFACES:
            continue
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for label, pattern in forbidden.items():
            if pattern.search(text):
                violations.append(f"{path.relative_to(REPO_ROOT)}: {label}")

    assert not violations, "\n".join(violations)


def test_current_project_surfaces_do_not_restore_former_identifiers():
    former_identifiers = (
        "breakout-turbo-env",
        "breakout_turbo_env",
        "Breakout-Turbo-v0",
        "_breakout_turbo",
    )
    violations: list[str] = []

    for path in _tracked_text_paths():
        if path.resolve() == Path(__file__).resolve():
            continue
        text = path.read_text(encoding="utf-8")
        for identifier in former_identifiers:
            if identifier in text:
                violations.append(f"{path.relative_to(REPO_ROOT)}: {identifier}")

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

    assert "Opt into raw frames" not in rendered_docs
    assert "raw emulator frames" not in environment_docs
    assert "Stable Retro-compatible" not in rendered_docs + environment_docs
    assert "with ALE, Stable Retro," not in benchmarking_docs
    assert "Stable Retro performs" not in benchmark_report


def test_benchmark_comparison_names_the_turbo_provider_explicitly():
    parser = build_parser()
    option_strings = {
        option
        for action in parser._actions
        for option in action.option_strings
    }

    assert "--stable-retro-turbo-repo" in option_strings
    assert "--stable-retro-repo" not in option_strings
