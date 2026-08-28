#!/usr/bin/env python3
"""Generate and verify the sole Stable Retro Turbo release-oracle receipt."""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import platform
import re
import subprocess
import sys
import urllib.request
from pathlib import Path
from urllib.parse import unquote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compare_stable_retro_turbo as comparison  # noqa: E402

CANDIDATE_PACKAGE = "env-breakoutatari2600-turbo-native"
CANDIDATE_MODULE = "env_breakoutatari2600_turbo_native"
SCHEMA = 1
KIND = "stable-retro-turbo-oracle-receipt"
CANONICAL_STEPS = 2_048
LIVE_WORKLOADS = comparison.LIVE_WORKLOADS
RESET_DISTRIBUTION_SEEDS = comparison.RESET_DISTRIBUTION_SEEDS
REQUIRED_TRAJECTORIES = ("cycling", "seeded-random")
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")


def git_output(*arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(REPO_ROOT), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "git command failed"
        raise ValueError(f"cannot identify candidate checkout: {detail}")
    return result.stdout.strip()


def receipt_provider(provider: object) -> dict[str, object]:
    if isinstance(provider, dict):
        value = provider
    else:
        value = vars(provider)
    keys = (
        "distribution",
        "module",
        "repository",
        "revision",
        "tree",
        "turbo_api_version",
        "version",
    )
    try:
        return {key: value[key] for key in keys}
    except KeyError as error:
        raise ValueError(f"provider pin is missing {error.args[0]!r}") from error


def canonical_workload() -> dict[str, object]:
    return {
        "id": "breakout/start-stable-retro-turbo-v1",
        "game": comparison.GAME,
        "steps_per_trajectory": CANONICAL_STEPS,
        "workloads": [
            {"name": name, "lane_count": lane_count}
            for name, lane_count in LIVE_WORKLOADS
        ],
        "trajectories": list(REQUIRED_TRAJECTORIES),
        "seeded_reset": {
            "noop_reset_max": 30,
            "seed_corpus": [
                RESET_DISTRIBUTION_SEEDS[0],
                RESET_DISTRIBUTION_SEEDS[-1],
            ],
            "seed_count": len(RESET_DISTRIBUTION_SEEDS),
            "maximum_cdf_distance": comparison.MAX_RESET_CDF_DISTANCE,
        },
        "environment": {
            "state": "Start",
            "scenario": "scenario",
            "info": "all",
            "actions": ["noop", "FIRE", "right", "left"],
            "render_mode": "rgb_array",
            "num_threads": 1,
            "observation": {
                "copy": "copy",
                "resize": [84, 84],
                "crop": [17, 0, 0, 0],
                "crop_mode": "mask",
                "crop_fill": 0,
                "grayscale": True,
                "resize_algorithm": "area",
                "layout": "chw",
                "frame_skip": 4,
                "frame_stack": 4,
                "maxpool_last_two": False,
            },
            "use_fire_reset": False,
            "sticky_action_prob": 0.0,
            "reward_clip": False,
        },
    }


def _project_version() -> str:
    version = (REPO_ROOT / "VERSION.txt").read_text(encoding="utf-8").strip()
    if VERSION_RE.fullmatch(version) is None:
        raise ValueError(f"candidate version is invalid: {version!r}")
    return version


def verify_installed_distribution(distribution) -> str:
    return comparison.verify_installed_distribution(distribution)


def _candidate_wheel_filename(version: str) -> str:
    machine = platform.machine().lower()
    prefix = f"env_breakoutatari2600_turbo_native-{version}-cp311-abi3-"
    if sys.platform == "darwin" and machine == "arm64":
        return f"{prefix}macosx_11_0_arm64.whl"
    if sys.platform.startswith("linux") and machine in {"x86_64", "amd64"}:
        return f"{prefix}manylinux_2_28_x86_64.whl"
    raise ValueError(
        "published candidate wheels support only macOS arm64 and Linux x86_64"
    )


def download_published_candidate(version: str, destination: Path) -> Path:
    if VERSION_RE.fullmatch(version) is None:
        raise ValueError("published candidate version must be exact X.Y.Z")
    filename = _candidate_wheel_filename(version)
    try:
        with urllib.request.urlopen(
            f"https://pypi.org/pypi/{CANDIDATE_PACKAGE}/{version}/json",
            timeout=30,
        ) as response:
            release = json.load(response)
    except (OSError, ValueError) as error:
        raise ValueError(f"cannot resolve the published candidate wheel: {error}") from error
    matches = [
        item
        for item in release.get("urls", [])
        if item.get("filename") == filename
        and item.get("packagetype") == "bdist_wheel"
    ]
    if len(matches) != 1:
        raise ValueError("the exact published candidate wheel is unavailable from PyPI")
    artifact = matches[0]
    digest = artifact.get("digests", {}).get("sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ValueError("the published candidate wheel digest is invalid")
    parsed_url = urlparse(artifact.get("url", ""))
    if parsed_url.scheme != "https" or parsed_url.hostname != "files.pythonhosted.org":
        raise ValueError("the published candidate wheel URL is not trusted")
    destination = destination.expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / filename
    temporary = output.with_suffix(".tmp")
    try:
        with urllib.request.urlopen(artifact["url"], timeout=120) as response:
            payload = response.read()
    except OSError as error:
        raise ValueError(f"cannot download the published candidate wheel: {error}") from error
    if hashlib.sha256(payload).hexdigest() != digest:
        raise ValueError("the downloaded candidate wheel digest changed")
    temporary.write_bytes(payload)
    temporary.replace(output)
    return output


def verify_checkout_source_binding(distribution) -> None:
    package = REPO_ROOT / "python" / CANDIDATE_MODULE
    sources = sorted(
        path
        for path in package.rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and (path.suffix in {".py", ".json"} or path.name == "py.typed")
    )
    if not sources:
        raise ValueError("candidate checkout package content is incomplete")
    for source in sources:
        relative = source.relative_to(REPO_ROOT / "python")
        installed = Path(distribution.locate_file(relative)).resolve()
        if not installed.is_file() or installed.read_bytes() != source.read_bytes():
            raise ValueError(
                f"installed candidate source content does not match checkout: {relative}"
            )


def candidate_distribution_identity(kind: str) -> dict[str, object]:
    distribution = importlib.metadata.distribution(CANDIDATE_PACKAGE)
    installed_record = verify_installed_distribution(distribution)
    module = importlib.import_module(CANDIDATE_MODULE)
    module_path = Path(module.__file__).resolve()
    installed_module = Path(distribution.locate_file(CANDIDATE_MODULE)).resolve()
    if not module_path.is_relative_to(installed_module):
        raise ValueError(
            "ambient candidate module does not come from the validated distribution"
        )
    version = importlib.metadata.version(CANDIDATE_PACKAGE)
    if module.__version__ != version:
        raise ValueError(
            "candidate module version does not match its installed distribution"
        )
    if kind == "checkout":
        verify_checkout_source_binding(distribution)

    direct_url_text = distribution.read_text("direct_url.json")
    if kind in {"checkout", "published-distribution"}:
        if not direct_url_text:
            raise ValueError("candidate was not installed from its exact wheel artifact")
        direct_url = json.loads(direct_url_text)
        parsed = urlparse(direct_url.get("url", ""))
        wheel = Path(unquote(parsed.path)).resolve() if parsed.scheme == "file" else None
        if wheel is None or wheel.suffix != ".whl" or not wheel.is_file():
            raise ValueError("candidate wheel origin is unavailable")
        if wheel.name != _candidate_wheel_filename(version):
            raise ValueError("candidate wheel identity does not match")
        source = "locally-built-wheel" if kind == "checkout" else "pypi"
        artifact_sha256 = hashlib.sha256(wheel.read_bytes()).hexdigest()
    else:
        raise ValueError("candidate distribution kind is not certifying")
    return {
        "installed_record_sha256": installed_record,
        "artifact": {"source": source, "sha256": artifact_sha256},
    }


def candidate_identity(
    selector: str,
    *,
    candidate_commit: str | None,
) -> dict[str, str]:
    is_checkout = selector == "checkout"
    is_published = VERSION_RE.fullmatch(selector) is not None
    if not is_checkout and not is_published:
        raise ValueError(
            "diagnostic candidate override cannot certify a release; use 'checkout' "
            "or an exact published X.Y.Z version"
        )
    if candidate_commit is not None and SHA_RE.fullmatch(candidate_commit) is None:
        raise ValueError("candidate commit must be a full lowercase 40-character SHA")
    dirty = git_output("status", "--porcelain", "--untracked-files=all")
    if dirty:
        raise ValueError(
            "certifying oracle validation requires a clean candidate checkout"
        )
    commit = git_output("rev-parse", "HEAD")
    if candidate_commit is not None and commit != candidate_commit:
        raise ValueError(
            f"candidate commit mismatch: expected {candidate_commit}, found {commit}"
        )

    if is_checkout:
        version = _project_version()
        installed_version = importlib.metadata.version(CANDIDATE_PACKAGE)
        if installed_version != version:
            raise ValueError(
                "installed checkout candidate version mismatch: "
                f"expected {version}, found {installed_version}"
            )
        return {
            "kind": "checkout",
            "package": CANDIDATE_PACKAGE,
            "version": version,
            "commit": commit,
            **candidate_distribution_identity("checkout"),
        }

    if is_published:
        if candidate_commit is None:
            raise ValueError("a published candidate requires its exact source commit")
        installed_version = importlib.metadata.version(CANDIDATE_PACKAGE)
        if installed_version != selector:
            raise ValueError(
                "installed published candidate version mismatch: "
                f"expected {selector}, found {installed_version}"
            )
        return {
            "kind": "published-distribution",
            "package": CANDIDATE_PACKAGE,
            "version": selector,
            "commit": candidate_commit,
            **candidate_distribution_identity("published-distribution"),
        }

    raise AssertionError("unreachable candidate selector")


def create_receipt(
    *,
    provider: object,
    candidate: dict[str, str],
    report: dict[str, object],
) -> dict[str, object]:
    return {
        "schema": SCHEMA,
        "kind": KIND,
        "provider": receipt_provider(provider),
        "candidate": candidate,
        "workload": canonical_workload(),
        "comparison": {"result": "exact", "report": report},
    }


def _require_mapping(value: object, label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _verify_report(report: object, provider: dict[str, object]) -> None:
    report = _require_mapping(report, "comparison report")
    report_provider = _require_mapping(report.get("provider"), "report provider")
    for key, expected in provider.items():
        if key == "repository":
            continue
        if report_provider.get(key) != expected:
            raise ValueError(f"comparison report provider pin {key!r} changed")
    if report_provider.get("artifact_source") != "isolated-pinned-wheel":
        raise ValueError("comparison report provider artifact source is not certifying")
    for field in ("installed_record_sha256", "artifact_sha256"):
        digest = report_provider.get(field)
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError(f"comparison report provider {field!r} is invalid")
    if set(report_provider) != {
        "distribution",
        "module",
        "version",
        "revision",
        "tree",
        "turbo_api_version",
        "installed_record_sha256",
        "artifact_sha256",
        "artifact_source",
    }:
        raise ValueError("comparison report provider identity is incomplete")

    workloads = _require_mapping(report.get("workloads"), "report workloads")
    expected_names = {name for name, _lane_count in LIVE_WORKLOADS}
    if set(workloads) != expected_names:
        raise ValueError("comparison report does not contain the canonical workloads")
    for name, lane_count in LIVE_WORKLOADS:
        workload = _require_mapping(workloads[name], f"{name} workload")
        if workload.get("lane_count") != lane_count:
            raise ValueError(f"{name} workload lane count changed")
        if workload.get("aligned_reset") != {"exact": True}:
            raise ValueError(f"{name} aligned reset was not exact")
        trajectories = _require_mapping(
            workload.get("trajectories"), f"{name} trajectories"
        )
        if set(trajectories) != set(REQUIRED_TRAJECTORIES):
            raise ValueError(f"{name} workload has incomplete trajectories")
        for trajectory_name in REQUIRED_TRAJECTORIES:
            trajectory = _require_mapping(
                trajectories[trajectory_name], f"{name} {trajectory_name} trajectory"
            )
            if trajectory.get("exact") is not True:
                raise ValueError(f"{name} {trajectory_name} trajectory was not exact")
            if trajectory.get("complete") is not True:
                raise ValueError(f"{name} {trajectory_name} trajectory was incomplete")
            if trajectory.get("maximum_steps") != CANONICAL_STEPS:
                raise ValueError(
                    f"{name} {trajectory_name} trajectory workload was incomplete"
                )
            steps = trajectory.get("steps")
            if type(steps) is not int or steps <= 0:
                raise ValueError(f"{name} {trajectory_name} trajectory executed no steps")
            if steps != CANONICAL_STEPS:
                raise ValueError(
                    f"{name} {trajectory_name} did not complete the fixed workload"
                )
            completed = trajectory.get("completed_episodes")
            if not isinstance(completed, list) or len(completed) != lane_count:
                raise ValueError(
                    f"{name} {trajectory_name} completion evidence is incomplete"
                )
            if trajectory.get("completion") != "step-limit":
                raise ValueError(
                    f"{name} {trajectory_name} did not complete the fixed workload"
                )
            if not all(type(value) is int and value >= 0 for value in completed):
                raise ValueError(
                    f"{name} {trajectory_name} completion evidence is invalid"
                )

        reset = _require_mapping(
            workload.get("seeded_reset_noops"), f"{name} seeded reset evidence"
        )
        if reset.get("exact") is not True or reset.get("counts") != list(range(1, 31)):
            raise ValueError(f"{name} seeded reset semantics were incomplete")
        distribution = _require_mapping(
            reset.get("distribution"), f"{name} reset distribution"
        )
        expected_distribution = {
            "matches": True,
            "lane_count": lane_count,
            "lane_sample_count": len(RESET_DISTRIBUTION_SEEDS),
            "seed_corpus": [
                RESET_DISTRIBUTION_SEEDS[0],
                RESET_DISTRIBUTION_SEEDS[-1],
            ],
            "maximum": 30,
        }
        for key, expected in expected_distribution.items():
            if distribution.get(key) != expected:
                raise ValueError(f"{name} reset distribution {key!r} changed")


def verify_receipt(
    receipt: object,
    *,
    candidate_version: str,
    candidate_commit: str,
) -> dict[str, object]:
    if VERSION_RE.fullmatch(candidate_version) is None:
        raise ValueError("candidate version must be an exact X.Y.Z release")
    if SHA_RE.fullmatch(candidate_commit) is None:
        raise ValueError("candidate commit must be a full lowercase 40-character SHA")
    receipt = _require_mapping(receipt, "oracle receipt")
    if set(receipt) != {
        "schema",
        "kind",
        "provider",
        "candidate",
        "workload",
        "comparison",
    }:
        raise ValueError("oracle receipt has incomplete or unexpected fields")
    if receipt.get("schema") != SCHEMA or receipt.get("kind") != KIND:
        raise ValueError("oracle receipt schema or kind is incompatible")

    expected_provider = receipt_provider(comparison.ProviderPin.load())
    provider = _require_mapping(receipt.get("provider"), "receipt provider")
    if provider != expected_provider:
        raise ValueError("oracle receipt provider pin does not match the operational pin")

    if receipt.get("workload") != canonical_workload():
        raise ValueError("oracle receipt does not bind the canonical workload configuration")

    candidate = _require_mapping(receipt.get("candidate"), "receipt candidate")
    if candidate.get("kind") not in {"checkout", "published-distribution"}:
        raise ValueError("oracle receipt candidate kind is diagnostic")
    if candidate.get("package") != CANDIDATE_PACKAGE:
        raise ValueError("oracle receipt candidate package changed")
    if candidate.get("version") != candidate_version:
        raise ValueError("oracle receipt candidate version does not match")
    if candidate.get("commit") != candidate_commit:
        raise ValueError("oracle receipt candidate commit does not match")
    record_digest = candidate.get("installed_record_sha256")
    artifact = _require_mapping(candidate.get("artifact"), "candidate artifact")
    if not isinstance(record_digest, str) or re.fullmatch(r"[0-9a-f]{64}", record_digest) is None:
        raise ValueError("oracle receipt candidate content ledger is invalid")
    if artifact.get("source") not in {"locally-built-wheel", "pypi"}:
        raise ValueError("oracle receipt candidate artifact source is invalid")
    if re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))) is None:
        raise ValueError("oracle receipt candidate artifact digest is invalid")
    if set(artifact) != {"source", "sha256"}:
        raise ValueError("oracle receipt candidate artifact identity is incomplete")
    if set(candidate) != {
        "kind",
        "package",
        "version",
        "commit",
        "installed_record_sha256",
        "artifact",
    }:
        raise ValueError("oracle receipt candidate identity is incomplete")

    comparison_result = _require_mapping(
        receipt.get("comparison"), "receipt comparison"
    )
    if comparison_result.get("result") != "exact":
        raise ValueError("oracle receipt comparison result is not exact")
    if set(comparison_result) != {"result", "report"}:
        raise ValueError("oracle receipt comparison result is incomplete")
    _verify_report(comparison_result.get("report"), provider)
    return receipt


def generate_receipt(
    *,
    provider_repo: Path,
    data_root: Path,
    candidate_selector: str,
    candidate_commit: str | None,
) -> dict[str, object]:
    inputs = comparison.preflight(provider_repo, data_root, certifying=True)
    candidate = candidate_identity(
        candidate_selector,
        candidate_commit=candidate_commit,
    )
    report = comparison.run_live_suite(inputs, steps=CANONICAL_STEPS)
    receipt = create_receipt(provider=inputs.pin, candidate=candidate, report=report)
    return verify_receipt(
        receipt,
        candidate_version=candidate["version"],
        candidate_commit=candidate["commit"],
    )


def write_receipt(path: Path, receipt: dict[str, object]) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _reject_duplicate_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key in oracle receipt: {key!r}")
        result[key] = value
    return result


def load_receipt(path: Path) -> dict[str, object]:
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_reject_duplicate_pairs,
    )
    return _require_mapping(value, "oracle receipt")


def verify_release_attestation(
    path: Path, repository: str, candidate_commit: str
) -> None:
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("release attestation repository must be exact owner/name")
    if SHA_RE.fullmatch(candidate_commit) is None:
        raise ValueError("release attestation candidate commit must be exact")
    result = subprocess.run(
        [
            "gh",
            "attestation",
            "verify",
            str(path),
            "--repo",
            repository,
            "--signer-workflow",
            f"{repository}/.github/workflows/oracle-evidence.yml",
            "--source-digest",
            candidate_commit,
            "--deny-self-hosted-runners",
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "verification failed"
        raise ValueError(f"oracle receipt lacks trusted GitHub provenance: {detail}")


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    commands = result.add_subparsers(dest="command", required=True)

    generate = commands.add_parser(
        "generate",
        help="run the fixed certifying workload and write a fail-closed receipt",
        description=(
            "Run the fixed certifying workload and write a fail-closed receipt; "
            "diagnostic workload and pytest overrides are intentionally unavailable."
        ),
    )
    generate.add_argument("--receipt", type=Path, required=True)
    generate.add_argument("--provider-repo", type=Path, required=True)
    generate.add_argument("--data-root", type=Path, required=True)
    generate.add_argument("--candidate", required=True)
    generate.add_argument("--candidate-commit")

    verify = commands.add_parser(
        "verify-local",
        help="NON-CERTIFYING: check receipt structure and bound comparison semantics",
    )
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--candidate-version", required=True)
    verify.add_argument("--candidate-commit", required=True)

    release = commands.add_parser(
        "verify-release",
        help="verify GitHub provenance and semantics for one exact release candidate",
    )
    release.add_argument("--receipt", type=Path, required=True)
    release.add_argument("--candidate-version", required=True)
    release.add_argument("--candidate-commit", required=True)
    release.add_argument("--repository", required=True)

    download = commands.add_parser(
        "download-published",
        help="download and hash the exact supported PyPI wheel for a candidate",
    )
    download.add_argument("--version", required=True)
    download.add_argument("--output-dir", type=Path, required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "download-published":
            wheel = download_published_candidate(args.version, args.output_dir)
            print(f"Published candidate wheel downloaded: {wheel}")
        elif args.command == "generate":
            receipt = generate_receipt(
                provider_repo=args.provider_repo,
                data_root=args.data_root,
                candidate_selector=args.candidate,
                candidate_commit=args.candidate_commit,
            )
            write_receipt(args.receipt, receipt)
            candidate = receipt["candidate"]
            print(
                "Stable Retro Turbo sole-oracle receipt generated for "
                f"{candidate['version']} at {candidate['commit']}: {args.receipt}"
            )
        elif args.command in {"verify-local", "verify-release"}:
            if args.command == "verify-release":
                verify_release_attestation(
                    args.receipt, args.repository, args.candidate_commit
                )
            receipt = load_receipt(args.receipt)
            verify_receipt(
                receipt,
                candidate_version=args.candidate_version,
                candidate_commit=args.candidate_commit,
            )
            print(f"Stable Retro Turbo sole-oracle receipt verified: {args.receipt}")
        else:
            raise AssertionError("unreachable oracle gate command")
    except (
        comparison.PreflightError,
        comparison.ObservableMismatch,
        importlib.metadata.PackageNotFoundError,
        json.JSONDecodeError,
        OSError,
        ValueError,
    ) as error:
        print(f"sole-oracle release gate failed: {error}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
