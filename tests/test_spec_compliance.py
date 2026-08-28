from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from importlib import util
from pathlib import Path

import pytest

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
    r"\b(?:"
    + "import"
    + r"\s+retro\b|from\s+retro(?:\.|\s+import\b)|"
    r"importlib\.import_module\(\s*(?:name\s*=\s*)?['\"]retro['\"]\s*\)|"
    r"from\s+importlib\s+import\s+import_module\s*;\s*"
    r"(?:retro\s*=\s*)?import_module\(\s*['\"]retro['\"]\s*\)|"
    r"(?:retro\s*=\s*)?import_module\(\s*['\"]retro['\"]\s*\)|"
    r"__import__\(\s*['\"]retro['\"]\s*\))",
    re.IGNORECASE,
)
_LEGACY_STABLE_RETRO_REFERENCE = re.compile(
    r"\b(?:original\s+)?Stable\s+Retro\b(?!\s+Turbo)",
    re.IGNORECASE,
)
_TURBO_REFERENCE = re.compile(r"\bStable\s+Retro\s+Turbo\b", re.IGNORECASE)
_REFERENCE_MARKER = "\0GUARDED_REFERENCE\0"
_TURBO_DEMOTION = (
    r"(?:secondary|fallback|supplemental|optional|alternative|backup|non-primary|"
    r"auxiliary|reserve|advisory)"
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
    return text


def _clauses(path: Path, text: str) -> list[str]:
    normalized = text
    if path.suffix.lower() in {".md", ".rst", ".txt"}:
        unquoted = re.sub(r"(?m)^[ \t]*>\s?", "", text)
        structural_breaks = re.sub(
            r"\n(?=\s*(?:[-*+]\s|\d+[.)]\s|#{1,6}\s|```))",
            "\n\n",
            unquoted,
        )
        normalized = re.sub(r"(?<!\n)\n(?!\n)", " ", structural_breaks)
    clauses: list[str] = []
    for sentence in re.split(r";|\n+|(?<=[.!?])\s+", normalized):
        if sentence.strip():
            clauses.append(sentence.strip())
    return clauses


def _mark_occurrence(text: str, start: int, end: int) -> str:
    return text[:start] + _REFERENCE_MARKER + text[end:]


def _distribution_is_denied(marked: str) -> bool:
    reference = re.escape(_REFERENCE_MARKER)
    if re.search(
        r"\b(?:but|yet|however|although|though|while|despite|nevertheless|"
        r"nonetheless|then|even\s+though|except\s+that)\b"
        r".{0,40}\b(?:install(?:ed|s)?|bundl(?:e|ed|es)|requir(?:e|ed|es)|"
        r"shipp(?:ed|s)|includ(?:e|ed|es))\b",
        marked,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"(?:\b(?:do\s+not|must\s+not|cannot|never)\s+"
            r"(?:directly\s+)?(?:(?:install|use|require)\s+|"
            r"depend\s+(?:directly\s+)?on\s+)"
            rf"(?:the\s+)?{reference}|"
            r"\b(?:does|do|must|should|can)\s+not\s+"
            r"(?:directly\s+)?(?:(?:include|install|use|require)\s+|"
            r"depend\s+(?:directly\s+)?on\s+)"
            rf"{reference}|{reference}.{{0,80}}\bnot\s+in\b|"
            rf"\bassert\s+not\b.{{0,80}}{reference}|"
            rf"{reference}\s+is\s+not\s+(?:a\s+)?required\b|"
            rf"{reference}\s+is\s+excluded\s+from\b|"
            rf"{reference}\s+remains\s+excluded\s+from\b|"
            rf"{reference}\s+is\s+(?:absent|forbidden)\s+(?:from|as)\b|"
            rf"{reference}\s+is\s+not\s+included\s+in\b|"
            rf"{reference}\s+must\s+remain\s+outside\b|"
            rf"{reference}\s+(?:is\s+not|must\s+not\s+be)\s+"
            rf"(?:an?\s+)?runtime\s+dependency\b|"
            rf"\bthe\s+runtime\s+has\s+no\s+{reference}\s+dependency\b|"
            rf"\bno\s+runtime\s+dependency\s+on\s+{reference}\s+exists\b|"
            rf"\b(?:do\s+not|must\s+not|cannot|never)\s+ship\s+{reference}|"
            rf"{reference}\s+must\s+not\s+be\s+bundled\b|"
            rf"\bno\s+{reference}\s+dependency\b.{{0,40}}\b(?:is\s+)?shipped\b)",
            marked,
            re.IGNORECASE,
        )
    )


def _direct_import_is_denied(marked: str) -> bool:
    if re.search(
        r"\b(?:but|yet|however|although|though|while|despite|nevertheless|"
        r"nonetheless|then|even\s+though|except\s+that)\b"
        r".{0,30}\bimports?\b",
        marked,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            r"(?:\b(?:do\s+not|must\s+not|cannot|never)\s+"
            + re.escape(_REFERENCE_MARKER)
            + r"|\b(?:does|do|must|should|can)\s+not\s+"
            + re.escape(_REFERENCE_MARKER)
            + r"|"
            + re.escape(_REFERENCE_MARKER)
            + r"\s+must\s+never\s+appear\b)",
            marked,
            re.IGNORECASE,
        )
    )


def _legacy_authority_is_denied(marked: str) -> bool:
    reference = re.escape(_REFERENCE_MARKER)
    authority = (
        r"(?:authoritative|authority|oracle|provider|release\s+gate|"
        r"compatibility\s+target)"
    )
    if re.search(
        rf"(?:\b(?:but|yet|however|although|though|while|despite|nevertheless|"
        rf"nonetheless|then|because|even\s+though|except\s+that)\b|[:,—–])"
        rf"\s*(?:it\s+)?(?:is|remains|serves|serving\s+as|acts|defines|should\s+be|"
        rf"should\s+be\s+used\s+to\s+validate)\b.{{0,40}}"
        rf"(?:\b{authority}\b|\bsource\s+of\s+truth\b|\bcanonical\s+behavior\b|"
        rf"\bexpected\s+results\b|\bvalidate\s+trajectories\b)",
        marked,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            rf"(?:\b(?:remove|removed|removing|deprecate|deprecated|purge|purged)\b\s+"
            rf"(?:the\s+)?{reference}\s+{authority}(?:\s+path)?|"
            rf"{reference}\s+(?:is|was)\s+not\s+(?:(?:the|an?)\s+)?"
            rf"(?:(?:project|canonical|semantic)\s+)?{authority}|"
            rf"{reference}\s+(?:must\s+not|must\s+never|cannot|never|no\s+longer)\s+"
            rf"(?:be\s+)?(?:used|treated|described|considered|serve|act)\b"
            rf".{{0,30}}\b(?:as\s+)?(?:an?\s+)?{authority}|"
            rf"\b(?:must\s+not|cannot|never)\s+"
            rf"(?:use|treat|describe|consider)\s+{reference}.{{0,30}}"
            rf"\b(?:as\s+)?(?:an?\s+)?{authority}|"
            rf"\b(?:do\s+not|must\s+not|cannot|never)\s+compare\b"
            rf".{{0,80}}\bagainst\s+{reference}|"
            rf"\b(?:do\s+not|must\s+not|cannot|never)\s+validate\b"
            rf".{{0,80}}\bagainst\s+{reference}|"
            rf"\bcanonical\b.{{0,80}}\bmust\s+not\s+match\s+{reference}|"
            rf"{reference}\s+is\s+not\s+(?:the\s+)?"
            rf"(?:source\s+of\s+truth|normative\s+reference|gold\s+standard)\b|"
            rf"{reference}.{{0,80}}\bonly\s+as\s+upstream\s+provenance\b"
            rf".{{0,80}}\bnever\s+as\s+an?\s+oracle\b|"
            rf"{reference}\s+(?:is\s+)?(?:cited\s+for\s+)?"
            rf"(?:upstream\s+provenance|legal\s+context)\b|"
            rf"{reference}\s+(?:appears|is\s+mentioned)\s+only\s+"
            rf"(?:as|for)\s+(?:upstream\s+provenance|legal\s+context)\b|"
            rf"{reference}\s+(?:appears|is\s+mentioned)\s+(?:only|solely)\s+"
            rf"(?:in|for)\s+(?:upstream\s+provenance|legal\s+context)\b|"
            rf"\bfor\s+legal\s+context\s+only\b.{{0,100}}{reference}|"
            rf"{reference}\s+is\s+retained\s+only\s+as\s+historical\s+context\b|"
            rf"{reference}\s+was\s+formerly\s+the\s+oracle\b|"
            rf"{reference}\s+predates\s+Stable\s+Retro\s+Turbo\b|"
            rf"\bmust\s+require\s+no\b.{{0,100}}{reference}|"
            rf"\b(?:does|do|must|should|can)\s+not\s+require\b.{{0,80}}{reference}|"
            rf"\b(?:does|do|must|should|can)\s+not\s+include\b.{{0,80}}{reference}|"
            rf"{reference}\s+is\s+not\s+required\b|"
            rf"\bno\s+{reference}\s+installation\b.{{0,40}}\brequired\b|"
            rf"\bno\s+installation\s+of\s+{reference}.{{0,40}}\brequired\b|"
            rf"\bnormal\s+use\b.{{0,80}}\b(?:works\s+without|requires\s+neither)\b"
            rf".{{0,80}}{reference}|"
            rf"{reference}\s+remains\s+absent\s+from\b|"
            rf"\bwithout\b.{{0,80}}{reference}\s+runtime\b|"
            rf"\bno\b.{{0,80}}{reference}\s+(?:runtime|save\s+state|installation)\b|"
            rf"\b_Avoid_:.{{0,100}}{reference}|"
            rf"\bnot\s+sponsored\b.{{0,80}}{reference}|"
            rf"\bnot\s+affiliated\b.{{0,120}}\bmaintainers\s+of\s+{reference}|"
            rf"\blawful\s+{reference}\s+(?:data|integration\s+data)\b|"
            rf"\bthird-party\s+notices\b.{{0,120}}{reference}.{{0,80}}\bboundaries\b|"
            rf"{reference}(?:'s|\s+1\.0\.1)\b.{{0,120}}"
            rf"\b(?:Stella|BGR|RGB565|rendered\s+frame|raw\s+transport)\b|"
            rf"\bassert\b.{{0,20}}{reference}.{{0,80}}\bnot\s+in\b)",
            marked,
            re.IGNORECASE,
        )
    )


def _turbo_secondary_is_denied(marked: str) -> bool:
    reference = re.escape(_REFERENCE_MARKER)
    if re.search(
        rf"(?:\b(?:but|yet|however|although|though|while|despite|nevertheless|"
        rf"nonetheless|then|because|even\s+though|except\s+that)\b|[:,—–])"
        rf"\s*(?:it\s+)?(?:is|remains|serves(?:\s+only)?\s+as|serving\s+as|"
        rf"may\s+be\s+used\s+as)\b.{{0,40}}"
        rf"(?:\b{_TURBO_DEMOTION}\b|\bone\s+of\s+several\s+oracles?\b|"
        rf"\bone\s+oracle\s+among\s+several\b)",
        marked,
        re.IGNORECASE,
    ):
        return False
    return bool(
        re.search(
            rf"(?:\b(?:prevent|prohibit|forbid|reject)(?:s|ed|ing)?\s+"
            rf"{reference}\s+from\s+being\s+(?:described|treated|used)\s+as\s+"
            rf"{_TURBO_DEMOTION}\b|"
            rf"{reference}\s+(?:must\s+not|cannot|never)\s+"
            rf"(?:be\s+)?(?:described|treated|used|serve)\s+as\s+(?:an?\s+)?"
            rf"{_TURBO_DEMOTION}\b|"
            rf"{reference}\s+(?:must\s+never|cannot)\s+be\s+"
            rf"(?:considered|treated)\s+(?:as\s+)?(?:an?\s+)?"
            rf"{_TURBO_DEMOTION}\b|"
            rf"\b(?:do\s+not|must\s+not|cannot|never)\s+"
            rf"(?:describe|treat|use)\s+{reference}\s+as\s+"
            rf"(?:an?\s+)?{_TURBO_DEMOTION}"
            rf"(?:\s+(?:oracle|provider|target|compatibility\s+target))?\b|"
            rf"{reference}.{{0,40}}\b(?:is\s+not|is\s+never)\s+"
            rf"(?:merely\s+)?(?:an?\s+)?{_TURBO_DEMOTION}"
            rf"(?:\s+(?:oracle|provider|target|compatibility\s+target))?\b|"
            rf"{reference}.{{0,40}}\bshould\s+not\s+be\s+{_TURBO_DEMOTION}\b|"
            rf"{reference}.{{0,40}}\bis\s+anything\s+but\s+{_TURBO_DEMOTION}\b|"
            rf"{reference}.{{0,40}}\bis\s+neither\s+{_TURBO_DEMOTION}\s+nor\s+"
            rf"{_TURBO_DEMOTION}\b|"
            rf"{reference}.{{0,50}}\bmust\s+never\s+be\s+regarded\s+as\s+"
            rf"(?:an?\s+)?{_TURBO_DEMOTION}\b|"
            rf"{reference}.{{0,60}}\bmust\s+under\s+no\s+circumstances\s+be\s+"
            rf"treated\s+as\s+(?:an?\s+)?{_TURBO_DEMOTION}\b|"
            rf"{reference}.{{0,50}}\b(?:sole\s+oracle|authoritative)\b"
            rf".{{0,40}}\b(?:not|never|cannot\s+be|rather\s+than)\s+"
            rf"(?:an?\s+)?{_TURBO_DEMOTION}\b|"
            rf"{reference}.{{0,50}}\bprimary(?:\s+oracle)?\b.{{0,40}}"
            rf"\b(?:not|never|cannot\s+be)\s+(?:an?\s+)?{_TURBO_DEMOTION}\b)",
            marked,
            re.IGNORECASE,
        )
    )


def _authority_violations(path: Path, text: str) -> list[str]:
    current = _current_authority_text(path, text)
    violations: list[str] = []

    for clause_number, clause in enumerate(_clauses(path, current), start=1):
        for match in _DIRECT_STABLE_RETRO_DISTRIBUTION.finditer(clause):
            marked = _mark_occurrence(clause, match.start(), match.end())
            if not _distribution_is_denied(marked):
                violations.append(
                    f"clause {clause_number}: direct legacy distribution"
                )
        for match in _DIRECT_STABLE_RETRO_IMPORT.finditer(clause):
            marked = _mark_occurrence(clause, match.start(), match.end())
            if not _direct_import_is_denied(marked):
                violations.append(f"clause {clause_number}: direct legacy import")
        for match in _LEGACY_STABLE_RETRO_REFERENCE.finditer(clause):
            marked = _mark_occurrence(clause, match.start(), match.end())
            if not _legacy_authority_is_denied(marked):
                violations.append(
                    f"clause {clause_number}: unapproved legacy authority"
                )
        for match in _TURBO_REFERENCE.finditer(clause):
            marked = _mark_occurrence(clause, match.start(), match.end())
            if re.search(
                rf"(?:{re.escape(_REFERENCE_MARKER)}.{{0,120}}\b{_TURBO_DEMOTION}\b|"
                rf"\b{_TURBO_DEMOTION}\b.{{0,120}}{re.escape(_REFERENCE_MARKER)}|"
                rf"{re.escape(_REFERENCE_MARKER)}.{{0,80}}\bnot\s+authoritative\b|"
                rf"{re.escape(_REFERENCE_MARKER)}.{{0,80}}\bone\s+of\b"
                rf".{{0,40}}\boracles?\b|"
                rf"{re.escape(_REFERENCE_MARKER)}.{{0,80}}\bone\s+oracle\s+among\s+several\b|"
                rf"{re.escape(_REFERENCE_MARKER)}.{{0,80}}\bsecond\s+oracle\b|"
                rf"{re.escape(_REFERENCE_MARKER)}.{{0,80}}\bneed\s+not\s+be\s+used\s+"
                rf"for\s+releases\b|"
                rf"{re.escape(_REFERENCE_MARKER)}.{{0,80}}\bdiagnostic\s+oracle\s+only\b)",
                marked,
                re.IGNORECASE,
            ) and not _turbo_secondary_is_denied(marked):
                violations.append(f"clause {clause_number}: sole-oracle demotion")

    return violations


def _former_identity_violations(path: Path, text: str) -> list[str]:
    current = _current_authority_text(path, text)
    violations: list[str] = []

    for clause_number, clause in enumerate(_clauses(path, current), start=1):
        for identifier in FORMER_IDENTIFIERS:
            escaped = re.escape(identifier)
            for match in re.finditer(escaped, clause):
                marked = _mark_occurrence(clause, match.start(), match.end())
                reference = re.escape(_REFERENCE_MARKER)
                historical = re.search(
                    rf"(?:\b(?:removed?|deprecated|purged|retired)\b.{{0,80}}{reference}"
                    rf".{{0,60}}\b(?:registration|identifier|command|name|entry\s+point)\b|"
                    rf"\b(?:removed?|deprecated|purged)\b\s+(?:the\s+)?"
                    rf"(?:legacy\s+)?(?:registration|identifier|command|name|entry\s+point)\s+"
                    rf"`?{reference}`?|"
                    rf"\b(?:renamed|replaced)\b.{{0,80}}{reference}|"
                    rf"{reference}\s+was\s+removed\s+as\s+(?:an?\s+)?"
                    rf"(?:registration|identifier|command|name|entry\s+point)\b|"
                    rf"{reference}\s+has\s+been\s+removed\s+as\s+(?:an?\s+)?"
                    rf"(?:registration|identifier|command|name|entry\s+point)\b|"
                    rf"{reference}\s+was\s+retired\s+as\s+(?:an?\s+)?"
                    rf"(?:registration|identifier|command|name|entry\s+point)\b|"
                    rf"\bsupport\s+for\s+{reference}\s+was\s+removed\b|"
                    rf"{reference}\s+is\s+no\s+longer\s+supported\b|"
                    rf"{reference}\s+is\s+unsupported\b|"
                    rf"{reference}\s+is\s+obsolete\b|"
                    rf"\b(?:do\s+not|must\s+not|cannot|never)\s+use\s+"
                    rf"{reference}\s+as\s+(?:the\s+)?(?:identifier|command|name)\b|"
                    rf"\bnever\s+invoke\s+{reference}|"
                    rf"\bdo\s+not\s+invoke\s+{reference}|"
                    rf"\bnever\s+run\s+{reference}|"
                    rf"{reference}\s+must\s+(?:not|never)\s+be\s+used\s+as\s+"
                    rf"(?:the\s+)?(?:identifier|command|name)\b|"
                    rf"\b(?:former|old|historical|deprecated)\s+"
                    rf"(?:name|identifier|command)\b.{{0,40}}{reference}"
                    rf".{{0,60}}\b(?:appears?\s+only\s+as\s+)?"
                    rf"(?:legal|upstream)\s+provenance\b)",
                    marked,
                    re.IGNORECASE,
                )
                current_support = re.search(
                    rf"(?:\b(?:register(?:ed)?|restore(?:d)?|reintroduc(?:e|ed)|"
                    rf"publish(?:ed)?|run|use|invoke)\b.{{0,80}}{reference}|"
                    rf"{reference}.{{0,80}}\b(?:remain(?:s|ed)?\s+supported|"
                    rf"(?:it\s+)?remain(?:s|ed)?\s+(?:accepted|active|valid)|"
                    rf"is\s+(?:accepted|active|valid|current|registered|restored|"
                    rf"reintroduced|published)|(?:it\s+)?still\s+works|"
                    rf"(?:callers?|users?)\s+(?:can|may)\s+still\s+invoke\s+it)\b)",
                    marked,
                    re.IGNORECASE,
                )
                denied = re.search(
                    rf"(?:{reference}\s+is\s+no\s+longer\s+supported\b|"
                    rf"{reference}\s+is\s+unsupported\b|"
                    rf"{reference}\s+is\s+obsolete\b|"
                    rf"\b(?:do\s+not|must\s+not|cannot|never)\s+use\s+"
                    rf"{reference}\s+as\s+(?:the\s+)?(?:identifier|command|name)\b|"
                    rf"\bnever\s+invoke\s+{reference}|"
                    rf"\bdo\s+not\s+invoke\s+{reference}|"
                    rf"\bnever\s+run\s+{reference}|"
                    rf"{reference}\s+must\s+(?:not|never)\s+be\s+used\s+as\s+"
                    rf"(?:the\s+)?(?:identifier|command|name)\b)",
                    marked,
                    re.IGNORECASE,
                )
                if denied:
                    continue
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
            "# Changelog\n\n## Unreleased\n\nStable" + " Retro Turbo is secondary.",
        ),
        (
            Path("docs/specification-compliance.md"),
            "Stable" + " Retro Turbo remains a secondary parity target.",
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
            "Prevent unrelated drift; Stable" + " Retro Turbo is secondary.",
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
    "text",
    [
        "Removed an obsolete note and Original Stable" + " Retro is the oracle.",
        "Do not use stale docs and install stable" + "-retro.",
        (
            "Prevent Stable"
            + " Retro Turbo from being described as secondary, but Stable"
            + " Retro Turbo is secondary."
        ),
    ],
)
def test_authority_guard_does_not_apply_unrelated_denial_to_later_claim(text):
    assert _authority_violations(Path("policy.md"), text)


@pytest.mark.parametrize(
    "text",
    [
        (
            "Original Stable"
            + " Retro is not an oracle, yet Original Stable"
            + " Retro is the oracle."
        ),
        "Do not install stable" + "-retro, then install stable" + "-retro for releases.",
        (
            "Stable"
            + " Retro Turbo is not secondary, yet Stable"
            + " Retro Turbo is secondary."
        ),
        "Original Stable" + " Retro is the sole semantic\noracle for canonical behavior.",
        "Stable" + " Retro Turbo is a\nsecondary compatibility target.",
    ],
)
def test_authority_guard_handles_connectives_and_wrapped_claims(text):
    assert _authority_violations(Path("policy.md"), text)


@pytest.mark.parametrize(
    "text",
    [
        (
            "Original Stable"
            + " Retro is not an oracle: Original Stable"
            + " Retro is the oracle."
        ),
        (
            "Stable"
            + " Retro Turbo is not secondary — Stable"
            + " Retro Turbo is secondary."
        ),
        (
            "Original Stable"
            + " Retro is not an oracle because Original Stable"
            + " Retro is the oracle."
        ),
        "> Original Stable" + " Retro is the sole semantic\n> oracle for behavior.",
        "> Stable" + " Retro Turbo is a\n> secondary compatibility target.",
        "Compare canonical `Start` against Original Stable" + " Retro.",
        "Canonical `Start` must match Original Stable" + " Retro.",
        "Original Stable" + " Retro defines the expected canonical behavior.",
        "Original Stable" + " Retro is the source of truth for Breakout behavior.",
        "Original Stable" + " Retro is the normative reference implementation.",
        "Breakout trajectories must be identical to Original Stable" + " Retro.",
        "Validate trajectories against Original Stable" + " Retro.",
        "Use Original Stable" + " Retro to certify releases.",
        "Original Stable" + " Retro is the gold standard.",
        "Stable" + " Retro Turbo is only a fallback oracle.",
        "Stable" + " Retro Turbo is a supplemental oracle.",
        (
            "__GUARDED_REFERENCE__ is not an oracle: Original Stable"
            + " Retro is the oracle."
        ),
        (
            "__GUARDED_REFERENCE__ is not secondary: Stable"
            + " Retro Turbo is secondary."
        ),
        "Do not install __GUARDED_REFERENCE__: install stable" + "-retro.",
        "Original Stable" + " Retro is not an oracle but is the oracle.",
        "Stable" + " Retro Turbo is not secondary but is secondary.",
        "> Original Stable" + " Retro is not an\n> oracle but is the oracle.",
        "Stable" + " Retro supplies the baseline for acceptance.",
        "Breakout trajectories must be identical to Stable" + " Retro.",
        "Expected results come from Stable" + " Retro.",
        "Treat Stable" + " Retro as the reference implementation.",
        "Stable" + " Retro defines canonical behavior.",
        "Stable" + " Retro determines expected behavior.",
        "Stable" + " Retro is the ground truth.",
        "Original Stable"
        + " Retro is not an oracle because it defines canonical behavior.",
        "Original Stable"
        + " Retro is not an oracle but should be used to validate trajectories.",
        "Original Stable" + " Retro is not an oracle although it is the oracle.",
        "Original Stable"
        + " Retro is not an oracle while it serves as the oracle.",
        "Original Stable" + " Retro is not an oracle but is the source of truth.",
        "Stable" + " Retro Turbo is not authoritative.",
        "Stable" + " Retro Turbo is one of two equivalent oracles.",
        "Stable" + " Retro Turbo is a diagnostic oracle only.",
        "Stable"
        + " Retro Turbo is not secondary, although it remains a fallback oracle.",
        "Stable"
        + " Retro Turbo should not be secondary but may be used as a fallback oracle.",
        "Stable"
        + " Retro Turbo is not secondary although it is a fallback oracle.",
        "Stable" + " Retro Turbo is a backup oracle.",
        "Stable" + " Retro Turbo is a non-primary oracle.",
        "stable" + "-retro is not required but it is installed for releases.",
        "stable"
        + "-retro must remain outside runtime dependencies but is bundled with releases.",
        "The code does not import" + " retro but imports it for releases.",
    ],
)
def test_authority_guard_evaluates_each_reference_occurrence(text):
    assert _authority_violations(Path("policy.md"), text)


@pytest.mark.parametrize(
    "text",
    [
        "Original Stable" + " Retro is not an oracle though it remains the oracle.",
        "Original Stable"
        + " Retro is not an oracle despite serving as the oracle.",
        "Original Stable"
        + " Retro is not an oracle even though it is authoritative.",
        "Original Stable"
        + " Retro is not the oracle except that it defines canonical behavior.",
        "Original Stable"
        + " Retro is not an oracle but remains the compatibility target.",
        "Original Stable"
        + " Retro is not the source of truth but defines expected results.",
        "Stable" + " Retro Turbo is not secondary though it remains a backup oracle.",
        "Stable"
        + " Retro Turbo is not a fallback oracle despite serving as an alternative oracle.",
        "Stable" + " Retro Turbo is the auxiliary oracle.",
        "Stable" + " Retro Turbo is a reserve oracle.",
        "Stable" + " Retro Turbo is a second oracle.",
        "Stable" + " Retro Turbo is one oracle among several.",
        "Stable" + " Retro Turbo is merely advisory.",
        "Stable" + " Retro Turbo need not be used for releases.",
        "Stable"
        + " Retro Turbo is not secondary because it serves only as a fallback oracle.",
        "Stable"
        + " Retro Turbo is not secondary but is one of several oracles.",
        "stable" + "-retro is not required, although releases install it.",
        "stable" + "-retro is not required though it is installed for releases.",
        "No stable" + "-retro dependency is shipped although the package includes it.",
        "retro = importlib." + "import_" + 'module("retro")',
        "retro = importlib." + "import_" + 'module(name="retro")',
        "from importlib import import_"
        + "module; import_"
        + 'module("retro")',
        "retro = __" + 'import__("retro")',
    ],
)
def test_authority_guard_blocks_final_reviewer_examples(text):
    assert _authority_violations(Path("policy.md"), text)


@pytest.mark.parametrize(
    "text",
    [
        "Stable" + " Retro Turbo is anything but secondary.",
        "Stable" + " Retro Turbo is neither secondary nor optional.",
        "Stable" + " Retro Turbo must never be regarded as secondary.",
        "Stable"
        + " Retro Turbo must under no circumstances be treated as secondary.",
        "Stable" + " Retro Turbo is the sole oracle, never a fallback.",
        "Stable" + " Retro Turbo is the sole oracle and cannot be a fallback.",
        "Stable" + " Retro Turbo is the primary oracle, never a backup.",
        "Stable" + " Retro Turbo is primary, not optional.",
        "stable" + "-retro is absent from runtime dependencies.",
        "stable" + "-retro is forbidden as a runtime dependency.",
        "stable" + "-retro is not included in runtime dependencies.",
        "No runtime dependency on stable" + "-retro exists.",
        "Original Stable" + " Retro appears only in upstream provenance.",
        "Original Stable" + " Retro is mentioned solely for legal context.",
        "For legal context only, this document mentions Original Stable" + " Retro.",
        "The runtime does not include Original Stable" + " Retro.",
        "No installation of Original Stable" + " Retro is required.",
        "Normal use requires neither Original Stable"
        + " Retro nor Stable Retro Turbo.",
        "Normal use works without an Original Stable" + " Retro installation.",
        "Original Stable" + " Retro remains absent from runtime dependencies.",
        "Original Stable" + " Retro is retained only as historical context.",
        "Original Stable" + " Retro was formerly the oracle.",
    ],
)
def test_authority_guard_allows_final_reviewer_examples(text):
    assert not _authority_violations(Path("policy.md"), text)


@pytest.mark.parametrize(
    ("path", "text"),
    [
        (
            Path("CHANGELOG.md"),
            "## [0.5.3] - 2026-08-12\n\nStable" + " Retro Turbo was secondary.",
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
            "Prevent Stable" + " Retro Turbo from being described as secondary.",
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
    "text",
    [
        "The Python distribution does not include stable" + "-retro.",
        "Original Stable" + " Retro is not an oracle.",
        "Original Stable" + " Retro is not the project oracle.",
        "Original Stable" + " Retro is not the canonical oracle.",
        "Original Stable" + " Retro is not a semantic oracle.",
        "Original Stable" + " Retro is not the canonical provider.",
        "Do not compare canonical Start against Original Stable" + " Retro.",
        "Canonical Start must not match Original Stable" + " Retro.",
        "Never depend directly on stable" + "-retro.",
        "Stable" + " Retro Turbo is not a secondary oracle.",
        "Stable" + " Retro Turbo must never be considered secondary.",
        "Never describe Stable"
        + " Retro Turbo as a secondary compatibility target.",
        "Stable" + " Retro Turbo should not be secondary.",
        "Stable"
        + " Retro Turbo cannot be used as a secondary compatibility target.",
        "Original Stable"
        + " Retro is upstream provenance because Stable Retro Turbo is the canonical oracle.",
        "Original Stable"
        + " Retro is cited for legal context because Stable Retro Turbo is the semantic oracle.",
        "Original Stable"
        + " Retro predates Stable Retro Turbo which is the sole oracle.",
        "stable" + "-retro is not required by the runtime.",
        "stable" + "-retro is excluded from core dependencies.",
        "No stable" + "-retro dependency is shipped.",
        "stable" + "-retro must remain outside runtime dependencies.",
        "The code does not import" + " retro.",
        "Original Stable" + " Retro must never serve as the semantic oracle.",
        "Do not validate against Original Stable" + " Retro.",
        "Original Stable" + " Retro is not the source of truth.",
        "Original Stable" + " Retro appears only as upstream provenance.",
        "Original Stable" + " Retro is mentioned only for legal context.",
        "Original Stable"
        + " Retro must never be treated as the canonical provider.",
        "The runtime does not require Original Stable" + " Retro.",
        "Original Stable" + " Retro is not required for normal use.",
        "No Original Stable" + " Retro installation is required.",
        "stable" + "-retro remains excluded from core dependencies.",
        "stable" + "-retro is not a runtime dependency.",
        "The runtime has no stable" + "-retro dependency.",
        "Do not ship stable" + "-retro.",
        "stable" + "-retro must not be bundled.",
        "stable" + "-retro must not be a runtime dependency.",
        "The phrase import" + " retro must never appear.",
        "Do not treat Stable" + " Retro Turbo as secondary.",
        "Never use Stable" + " Retro Turbo as a fallback oracle.",
        "Stable" + " Retro Turbo cannot serve as an alternative oracle.",
        "Stable" + " Retro Turbo is the sole oracle, not a fallback.",
        "Stable" + " Retro Turbo is authoritative rather than secondary.",
        "Stable"
        + " Retro Turbo must never be treated as a secondary provider.",
        "Stable" + " Retro Turbo is never merely secondary.",
    ],
)
def test_authority_guard_allows_reference_local_denials(text):
    assert not _authority_violations(Path("policy.md"), text)


def test_versioned_benchmark_records_are_scanned_for_current_authority_claims():
    path = Path("docs/benchmarks/v9.9.9-test.md")

    assert _authority_violations(path, "Original Stable" + " Retro is the oracle.")
    assert _former_identity_violations(
        path, "Use Breakout" + "Turbo-v0 as the command."
    )


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


def test_former_identity_guard_rejects_unrelated_history_in_same_sentence():
    assert _former_identity_violations(
        Path("README.md"),
        "Removed an obsolete note and use Breakout" + "Turbo-v0 as the command.",
    )
    assert _former_identity_violations(
        Path("README.md"),
        "Removed command Breakout"
        + "Turbo-v0 but it remains supported.",
    )
    assert _former_identity_violations(
        Path("README.md"),
        "Removed command __GUARDED_REFERENCE__: Breakout"
        + "Turbo-v0 is the active environment ID.",
    )


def test_former_identity_guard_handles_comma_connectives():
    assert _former_identity_violations(
        Path("README.md"),
        "Removed command Breakout"
        + "Turbo-v0, then use Breakout"
        + "Turbo-v0 as the command.",
    )


@pytest.mark.parametrize(
    "text",
    [
        "Removed command Breakout" + "Turbo-v0 although it remains accepted.",
        "Removed command Breakout" + "Turbo-v0 but it remains active.",
        "Removed command Breakout" + "Turbo-v0 but it remains valid.",
        "Removed command Breakout" + "Turbo-v0 but it still works.",
        "Removed command Breakout" + "Turbo-v0 but users may still invoke it.",
    ],
)
def test_former_identity_guard_blocks_final_reviewer_examples(text):
    assert _former_identity_violations(Path("policy.md"), text)


@pytest.mark.parametrize(
    "text",
    [
        "Breakout" + "Turbo-v0 was retired as a command.",
        "Breakout" + "Turbo-v0 is obsolete.",
        "Do not invoke Breakout" + "Turbo-v0.",
        "Never run Breakout" + "Turbo-v0.",
        "Breakout" + "Turbo-v0 must never be used as the command.",
    ],
)
def test_former_identity_guard_allows_final_reviewer_examples(text):
    assert not _former_identity_violations(Path("policy.md"), text)


def test_former_identity_guard_allows_narrow_historical_mentions():
    assert not _former_identity_violations(
        Path("CHANGELOG.md"),
        "Removed command breakout" + "-turbo-env.",
    )
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
    assert not _former_identity_violations(
        Path("CHANGELOG.md"),
        "Breakout" + "Turbo-v0 was removed as a command.",
    )
    assert not _former_identity_violations(
        Path("policy.md"),
        "Breakout" + "Turbo-v0 is no longer supported.",
    )
    assert not _former_identity_violations(
        Path("policy.md"),
        "Do not use Breakout" + "Turbo-v0 as the command.",
    )
    for text in (
        "Renamed Breakout" + "Turbo-v0 to the new command, which users now use.",
        "Removed command Breakout" + "Turbo-v0: use env-current instead.",
        "Breakout" + "Turbo-v0 has been removed as a command.",
        "Support for Breakout" + "Turbo-v0 was removed.",
        "Breakout" + "Turbo-v0 is unsupported.",
        "Never invoke Breakout" + "Turbo-v0.",
        "Breakout" + "Turbo-v0 must not be used as the command.",
    ):
        assert not _former_identity_violations(Path("policy.md"), text)


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
        path for path in tracked if path.suffix.lower() in forbidden_suffixes
    ]
    package_data = [
        path
        for path in tracked
        if path.parts[:2] == ("python", "env_breakoutatari2600_turbo_native")
        and "data" in path.parts
    ]
    metadata = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

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
