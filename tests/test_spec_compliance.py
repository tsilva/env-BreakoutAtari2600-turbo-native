from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib import util
from pathlib import Path

import pytest

from scripts.benchmark_comparison import build_parser

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPLIANCE_MATRIX = REPO_ROOT / "docs" / "specification-compliance.md"
FORMER_IDENTIFIERS = (
    "breakout" + "-turbo-env",
    "breakout" + "_turbo_env",
    "Breakout" + "-Turbo-v0",
    "Breakout" + "Turbo-v0",
    "_breakout" + "_turbo",
    "Breakout" + " Turbo",
    "breakout" + "-turbo-benchmark",
    "breakout" + "-turbo-play",
)
_DIRECT_STABLE_RETRO_DISTRIBUTION = re.compile(
    r"(?<![\w-])" + "stable" + r"-retro(?!-turbo)(?![\w-])", re.IGNORECASE
)
_DIRECT_STABLE_RETRO_IMPORT = re.compile(
    r"\b(?:" + "import" + r"\s+retro\b|from\s+retro(?:\.|\s+import\b))",
    re.IGNORECASE,
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


@dataclass(frozen=True)
class TrackedBlob:
    path: Path
    mode: str
    oid: str
    content: bytes


def _spec_requirements() -> list[str]:
    return [
        line.removeprefix("- ")
        for line in (REPO_ROOT / "SPECS.md").read_text(encoding="utf-8").splitlines()
        if line.startswith("- ")
    ]


def _matrix_requirements() -> list[str]:
    text = COMPLIANCE_MATRIX.read_text(encoding="utf-8")
    return re.findall(r"^<!-- SPECS:\d+ -->\n> (.+)$", text, flags=re.MULTILINE)


def _tracked_blobs() -> list[TrackedBlob]:
    result = subprocess.run(
        ["git", "ls-files", "-s", "-z"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    entries: list[tuple[Path, str, str]] = []
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", maxsplit=1)
        mode, raw_oid, stage = metadata.split()
        if stage != b"0":
            raise AssertionError(f"unsupported tracked merge stage: {stage!r}")
        try:
            path = Path(raw_path.decode("utf-8"))
        except UnicodeDecodeError as error:
            raise AssertionError("tracked path is not valid UTF-8") from error
        entries.append((path, mode.decode("ascii"), raw_oid.decode("ascii")))

    blob_result = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=REPO_ROOT,
        input="".join(f"{oid}\n" for _, _, oid in entries).encode("ascii"),
        check=True,
        capture_output=True,
    )
    output = blob_result.stdout
    offset = 0
    blobs: list[TrackedBlob] = []
    for path, mode, expected_oid in entries:
        header_end = output.index(b"\n", offset)
        actual_oid, object_type, raw_size = output[offset:header_end].split()
        if object_type != b"blob" or actual_oid.decode("ascii") != expected_oid:
            raise AssertionError(f"unexpected tracked object for {path}")
        size = int(raw_size)
        start = header_end + 1
        content = output[start : start + size]
        if output[start + size : start + size + 1] != b"\n":
            raise AssertionError(f"malformed tracked blob response for {path}")
        blobs.append(TrackedBlob(path, mode, expected_oid, content))
        offset = start + size + 1
    if offset != len(output):
        raise AssertionError("unexpected trailing tracked blob data")
    return sorted(blobs, key=lambda blob: blob.path.as_posix())


def _tracked_paths() -> list[Path]:
    return [REPO_ROOT / blob.path for blob in _tracked_blobs()]


def _decode_tracked_text(blob: TrackedBlob) -> str | None:
    if blob.mode == "120000":
        raise AssertionError(f"unsupported tracked symlink: {blob.path}")
    if blob.mode not in {"100644", "100755"}:
        raise AssertionError(f"unsupported tracked mode {blob.mode}: {blob.path}")
    if b"\0" in blob.content:
        return None
    try:
        return blob.content.decode("utf-8")
    except UnicodeDecodeError as error:
        raise AssertionError(
            f"tracked text candidate is not valid UTF-8: {blob.path}"
        ) from error


def _tracked_texts() -> list[tuple[Path, str]]:
    text_blobs: list[tuple[Path, str]] = []
    for blob in _tracked_blobs():
        text = _decode_tracked_text(blob)
        if text is not None:
            text_blobs.append((blob.path, text))
    return text_blobs


def _current_authority_text(path: Path, text: str) -> str:
    relative = path.as_posix()
    if relative == "CHANGELOG.md":
        return re.split(r"^## \[", text, maxsplit=1, flags=re.MULTILINE)[0]
    if re.fullmatch(r"docs/benchmarks/v\d[^/]*\.md", relative):
        return ""
    return text


def _clauses(text: str) -> list[str]:
    return [
        clause.strip()
        for clause in re.split(r";|\n|(?<=[.!?])\s+", text)
        if clause.strip()
    ]


def _distribution_is_denied(clause: str) -> bool:
    return bool(
        re.search(
            r"(?:\b(?:do\s+not|must\s+not|cannot|never)\s+"
            r"(?:directly\s+)?(?:install|use|depend\s+on|require)\b.{0,40}"
            + "stable"
            + r"-retro\b|"
            + "stable"
            + r"-retro\b.{0,80}\bnot\s+in\b|"
            r"\bassert\s+not\b.{0,80}" + "stable" + r"-retro\b)",
            clause,
            re.IGNORECASE,
        )
    )


def _direct_import_is_denied(clause: str) -> bool:
    return bool(
        re.search(
            r"\b(?:do\s+not|must\s+not|cannot|never)\s+" + "import" + r"\s+retro\b",
            clause,
            re.IGNORECASE,
        )
    )


def _original_authority_is_denied(clause: str) -> bool:
    original = r"(?:original\s+)?Stable\s+Retro\b(?!\s+Turbo)"
    authority = r"(?:authoritative|authority|oracle|provider|release\s+gate)"
    return bool(
        re.search(
            rf"(?:\b(?:remove|removed|removing|deprecate|deprecated|purge|purged)\b"
            rf".{{0,40}}{original}.{{0,30}}{authority}(?:\s+path)?|"
            rf"{original}\s+(?:must\s+not|cannot|never|no\s+longer)\s+"
            rf"(?:be\s+)?(?:used|treated|described|considered|serve|act)\b"
            rf".{{0,30}}\b(?:as\s+)?(?:an?\s+)?{authority}|"
            rf"\b(?:must\s+not|cannot|never)\s+"
            rf"(?:use|treat|describe|consider)\s+{original}.{{0,30}}"
            rf"\b(?:as\s+)?(?:an?\s+)?{authority}|"
            rf"{original}.{{0,80}}\bonly\s+as\s+upstream\s+provenance\b"
            rf".{{0,80}}\bnever\s+as\s+an?\s+oracle\b)",
            clause,
            re.IGNORECASE,
        )
    )


def _turbo_secondary_is_denied(clause: str) -> bool:
    turbo = r"Stable\s+Retro\s+Turbo"
    return bool(
        re.search(
            rf"(?:\b(?:prevent|prohibit|forbid|reject)(?:s|ed|ing)?\s+"
            rf"{turbo}\s+from\s+being\s+(?:described|treated|used)\s+as\s+secondary\b|"
            rf"{turbo}\s+(?:must\s+not|cannot|never)\s+"
            rf"(?:be\s+)?(?:described|treated|used)\s+as\s+secondary\b|"
            rf"{turbo}.{{0,40}}\b(?:is\s+not|is\s+never)\s+secondary\b)",
            clause,
            re.IGNORECASE,
        )
    )


def _authority_violations(path: Path, text: str) -> list[str]:
    current = _current_authority_text(path, text)
    violations: list[str] = []

    for clause_number, clause in enumerate(_clauses(current), start=1):
        if _DIRECT_STABLE_RETRO_DISTRIBUTION.search(
            clause
        ) and not _distribution_is_denied(clause):
            violations.append(f"clause {clause_number}: direct legacy distribution")
        if _DIRECT_STABLE_RETRO_IMPORT.search(clause) and not _direct_import_is_denied(
            clause
        ):
            violations.append(f"clause {clause_number}: direct legacy import")
        if _DIRECT_STABLE_RETRO_AUTHORITY.search(
            clause
        ) and not _original_authority_is_denied(clause):
            violations.append(f"clause {clause_number}: unapproved legacy authority")
        if _TURBO_SECONDARY.search(clause) and not _turbo_secondary_is_denied(clause):
            violations.append(f"clause {clause_number}: sole-oracle demotion")

    return violations


def _former_identity_violations(path: Path, text: str) -> list[str]:
    current = _current_authority_text(path, text)
    violations: list[str] = []

    for clause_number, clause in enumerate(_clauses(current), start=1):
        for identifier in FORMER_IDENTIFIERS:
            if identifier not in clause:
                continue
            escaped = re.escape(identifier)
            historical = re.search(
                rf"(?:\b(?:removed?|deprecated|purged)\b.{{0,80}}{escaped}"
                rf".{{0,60}}\b(?:registration|identifier|command|name|entry\s+point)\b|"
                rf"\b(?:renamed|replaced)\b.{{0,80}}{escaped}|"
                rf"\b(?:former|old|historical|deprecated)\s+"
                rf"(?:name|identifier|command)\b.{{0,40}}{escaped}"
                rf".{{0,60}}\b(?:appears?\s+only\s+as\s+)?"
                rf"(?:legal|upstream)\s+provenance\b)",
                clause,
                re.IGNORECASE,
            )
            current_support = re.search(
                r"\b(?:remain(?:s|ed)?|supported|accepted|current|register(?:ed)?|"
                r"restore(?:d)?|reintroduc(?:e|ed)|publish(?:ed)?|run)\b",
                clause,
                re.IGNORECASE,
            )
            if historical and not current_support:
                continue
            violations.append(f"clause {clause_number}: {identifier}")

    return violations


def test_compliance_matrix_maps_every_spec_requirement_literally_and_in_order():
    requirements = _spec_requirements()

    assert len(requirements) == 33
    assert _matrix_requirements() == requirements


def _blob(
    path: str,
    content: bytes,
    *,
    mode: str = "100644",
) -> TrackedBlob:
    return TrackedBlob(Path(path), mode, "0" * 40, content)


@pytest.mark.parametrize("name", ["guard.sh", "Cargo.lock", "release-tool"])
def test_tracked_text_detection_is_content_based(name):
    content = ("import" + " retro\n").encode()

    assert _decode_tracked_text(_blob(name, content)) == content.decode()


def test_tracked_text_detection_skips_nul_marked_binary_content():
    blob = _blob("extensionless", b"text prefix\x00binary payload")

    assert _decode_tracked_text(blob) is None


def test_tracked_text_detection_fails_closed_on_invalid_utf8():
    with pytest.raises(AssertionError, match="not valid UTF-8"):
        _decode_tracked_text(_blob("guard.sh", b"text prefix\xffpayload"))


def test_tracked_text_detection_fails_closed_on_symlinks_without_dereference():
    with pytest.raises(AssertionError, match="unsupported tracked symlink"):
        _decode_tracked_text(_blob("current-contract", b"README.md", mode="120000"))


def test_tracked_text_enumeration_has_no_suffix_or_executable_name_allowlist(
    monkeypatch,
):
    text_blobs = [
        _blob(name, b"current contract\n")
        for name in ("guard.sh", "Cargo.lock", "release-tool")
    ]
    binary = _blob("generated-image", b"image\x00payload")
    monkeypatch.setattr(
        sys.modules[__name__], "_tracked_blobs", lambda: [*text_blobs, binary]
    )

    assert _tracked_texts() == [
        (blob.path, "current contract\n") for blob in text_blobs
    ]


@pytest.mark.parametrize(
    ("path", "text"),
    [
        (
            Path("README.md"),
            "Original Stable" + " Retro is the authoritative oracle.",
        ),
        (Path("release.sh"), "pip install stable" + "-retro"),
        (Path("release-tool"), "import" + " retro"),
        (
            Path("CHANGELOG.md"),
            "# Changelog\n\n## Unreleased\n\nStable Retro" + " Turbo is secondary.",
        ),
        (
            Path("docs/specification-compliance.md"),
            "Stable Retro" + " Turbo remains a secondary parity target.",
        ),
        (
            Path("policy.md"),
            "Never write cache files; pip install stable" + "-retro",
        ),
        (
            Path("policy.md"),
            "Removed an obsolete note; Original Stable" + " Retro is the oracle.",
        ),
        (
            Path("policy.md"),
            "Prevent unrelated drift; Stable Retro" + " Turbo is secondary.",
        ),
        (
            Path("policy.md"),
            "Prevent stale wording; import" + " retro",
        ),
        (
            Path("policy.md"),
            "Never demote Turbo; pip install stable" + "-retro",
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
            "## [0.5.3] - 2026-08-12\n\nStable Retro" + " Turbo was secondary.",
        ),
        (
            Path("CHANGELOG.md"),
            "## Unreleased\n\nRemoved the original Stable" + " Retro authority path.",
        ),
        (
            Path("THIRD_PARTY_NOTICES.md"),
            "The project is not sponsored by the maintainers of Stable" + " Retro.",
        ),
        (
            Path("CONTRIBUTING.md"),
            "Original Stable"
            + " Retro may appear only as upstream provenance, never as an oracle.",
        ),
        (Path("Makefile"), 'assert "stable' + '-retro@" not in makefile'),
        (Path("provider.py"), "import env_stableretro_turbo as retro"),
        (
            Path("docs/policy.md"),
            "Prevent Stable Retro" + " Turbo from being described as secondary.",
        ),
        (
            Path("docs/policy.md"),
            "Original Stable" + " Retro must not be used as an oracle.",
        ),
    ],
)
def test_authority_guard_allows_negation_provenance_and_versioned_history(path, text):
    assert not _authority_violations(path, text)


@pytest.mark.parametrize(
    "identifier",
    FORMER_IDENTIFIERS,
)
def test_former_identity_guard_rejects_each_known_identifier(identifier):
    text = f"Register {identifier} as the current public command or environment ID."

    assert _former_identity_violations(Path("README.md"), text)


@pytest.mark.parametrize(
    "text",
    [
        "Removed an obsolete note; run Breakout" + "Turbo-v0.",
        "For historical reasons, Breakout" + "Turbo-v0 remains supported.",
        "The former identifier Breakout"
        + "Turbo-v0 remains an accepted environment ID.",
    ],
)
def test_former_identity_guard_rejects_unrelated_or_current_history_claims(text):
    assert _former_identity_violations(Path("README.md"), text)


def test_former_identity_guard_allows_narrow_historical_mentions():
    assert not _former_identity_violations(
        Path("CHANGELOG.md"),
        "## Unreleased\n\nRemoved the legacy `Breakout" + "Turbo-v0` registration.",
    )
    assert not _former_identity_violations(
        Path("CHANGELOG.md"),
        "## [0.5.0] - 2026-07-27\n\nThe old command was `breakout" + "-turbo-env`.",
    )
    assert not _former_identity_violations(
        Path("THIRD_PARTY_NOTICES.md"),
        "The former name `Breakout" + " Turbo` appears only as legal provenance.",
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
    module_spec = util.spec_from_file_location(
        "release_build_for_compliance",
        REPO_ROOT / release_helper,
    )
    assert module_spec is not None and module_spec.loader is not None
    release_build = util.module_from_spec(module_spec)
    module_spec.loader.exec_module(release_build)
    release_parser = release_build.build_parser()

    platform_args = release_parser.parse_args(
        ["build-platform", "--platform", "macos-arm64"]
    )
    assert platform_args.platform == "macos-arm64"
    assert platform_args.func is release_build.build_platform
    sdist_args = release_parser.parse_args(["build-sdist"])
    assert sdist_args.func is release_build.build_sdist
    with pytest.raises(SystemExit):
        release_parser.parse_args(["build-platform"])


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
    for path, text in _tracked_texts():
        violations.extend(
            f"{path}: {finding}" for finding in _authority_violations(path, text)
        )

    assert not violations, "\n".join(violations)


def test_current_project_surfaces_do_not_restore_former_identifiers():
    violations: list[str] = []

    for path, text in _tracked_texts():
        violations.extend(
            f"{path}: {finding}" for finding in _former_identity_violations(path, text)
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
    public_api = "\n".join(
        text
        for path, text in _tracked_texts()
        if path.parts[:2] == ("python", "env_breakoutatari2600_turbo_native")
        and path.suffix == ".py"
    )
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
    assert "Stable Retro-compatible actions" not in public_api
    assert "Stable-compatible filtered actions" in public_api
    assert "eight-button transport" in public_api
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
