#!/usr/bin/env python3
"""Generate and verify the sole Stable Retro Turbo release-oracle receipt."""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import re
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import compare_stable_retro_turbo as comparison  # noqa: E402

CANDIDATE_PACKAGE = "env-breakoutatari2600-turbo-native"
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
        distribution = importlib.metadata.distribution(CANDIDATE_PACKAGE)
        if distribution.read_text("direct_url.json"):
            raise ValueError(
                "diagnostic candidate override cannot certify a release; install the "
                "exact published distribution from the package index"
            )
        return {
            "kind": "published-distribution",
            "package": CANDIDATE_PACKAGE,
            "version": selector,
            "commit": candidate_commit,
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
            if steps > CANONICAL_STEPS:
                raise ValueError(f"{name} {trajectory_name} trajectory exceeded workload")
            completed = trajectory.get("completed_episodes")
            if not isinstance(completed, list) or len(completed) != lane_count:
                raise ValueError(
                    f"{name} {trajectory_name} completion evidence is incomplete"
                )
            if trajectory.get("completion") == "step-limit":
                if steps != CANONICAL_STEPS or any(completed):
                    raise ValueError(
                        f"{name} {trajectory_name} did not complete the fixed workload"
                    )
            elif trajectory.get("completion") == "episode-ended":
                if not any(type(value) is int and value > 0 for value in completed):
                    raise ValueError(
                        f"{name} {trajectory_name} lacks terminal completion evidence"
                    )
            else:
                raise ValueError(f"{name} {trajectory_name} completion kind changed")

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
    if set(candidate) != {"kind", "package", "version", "commit"}:
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
    inputs = comparison.preflight(provider_repo, data_root)
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
        "verify", help="verify a receipt for one exact release candidate"
    )
    verify.add_argument("--receipt", type=Path, required=True)
    verify.add_argument("--candidate-version", required=True)
    verify.add_argument("--candidate-commit", required=True)
    return result


def main() -> int:
    args = parser().parse_args()
    try:
        if args.command == "generate":
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
        else:
            receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
            verify_receipt(
                receipt,
                candidate_version=args.candidate_version,
                candidate_commit=args.candidate_commit,
            )
            print(f"Stable Retro Turbo sole-oracle receipt verified: {args.receipt}")
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
