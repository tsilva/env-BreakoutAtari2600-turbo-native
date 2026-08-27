#!/usr/bin/env python3
"""Compare canonical Breakout trajectories with the pinned Stable Retro Turbo oracle."""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import numpy as np

GAME = "Breakout-Atari2600-v0"
REPO_ROOT = Path(__file__).resolve().parents[1]
PIN_PATH = REPO_ROOT / "validation/stable-retro-turbo.json"
REQUIRED_DATA_FILES = ("rom.a26",)
REQUIRED_PROVIDER_INTEGRATION_FILES = (
    "Start.state",
    "data.json",
    "scenario.json",
)
ACTION_TABLE = ((), ("BUTTON",), ("RIGHT",), ("LEFT",))
REQUIRED_SHARED_INFO = ("ball_y", "lives", "score")
RESET_DISTRIBUTION_SEEDS = tuple(range(256))
# Each of 256 independent reset seeds exercises both lanes, producing 512 public
# observations per provider. At effective n=256, the two-sample KS 1% critical
# distance is approximately 1.63 * sqrt(2 / 256) = 0.144; 0.15 is conservative.
MAX_RESET_CDF_DISTANCE = 0.15


def canonicalize_provider_frame(frame: np.ndarray) -> np.ndarray:
    """Convert Turbo's inherited BGR-labeled RGB565 transport to Stella RGB."""
    canonical = np.asarray(frame, dtype=np.uint8)[..., ::-1].copy()
    canonical &= np.array([0xF8, 0xFC, 0xF8], dtype=np.uint8)
    corrections = {
        (136, 140, 136): (136, 136, 136),
        (192, 108, 56): (192, 104, 56),
        (64, 156, 128): (64, 152, 128),
    }
    for source, target in corrections.items():
        canonical[np.all(canonical == source, axis=2)] = target
    return canonical


class PreflightError(RuntimeError):
    """A required external oracle input is absent or incompatible."""


class ObservableMismatch(AssertionError):
    """The native environment disagreed with an oracle observable."""


@dataclass(frozen=True)
class ProviderPin:
    distribution: str
    module: str
    repository: str
    revision: str
    turbo_api_version: int
    version: str

    @classmethod
    def load(cls) -> ProviderPin:
        try:
            payload = json.loads(PIN_PATH.read_text(encoding="utf-8"))
            return cls(**payload)
        except (OSError, TypeError, ValueError) as error:
            raise PreflightError(f"cannot read oracle pin {PIN_PATH}: {error}") from error


@dataclass(frozen=True)
class OracleInputs:
    pin: ProviderPin
    provider_repo: Path
    data_dir: Path
    provider_data_dir: Path


def _git_head(repository: Path) -> str:
    result = subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or "not a Git checkout"
        raise PreflightError(
            f"cannot identify Stable Retro Turbo provider revision at "
            f"{repository}: {detail}"
        )
    return result.stdout.strip()


def _prepare_provider_checkout(
    provider_repo: Path,
    destination: Path,
    *,
    revision: str,
) -> Path:
    tree = subprocess.run(
        [
            "git",
            "-C",
            str(provider_repo),
            "ls-tree",
            "-r",
            revision,
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if tree.returncode != 0:
        detail = tree.stderr.strip() or "cannot inspect pinned tree"
        raise PreflightError(
            f"cannot inspect pinned Stable Retro Turbo provider tree: {detail}"
        )
    submodules = [
        line.partition("\t")[2]
        for line in tree.stdout.splitlines()
        if line.startswith("160000 ")
    ]
    if submodules:
        raise PreflightError(
            "pinned Stable Retro Turbo provider contains unsupported submodules: "
            f"{', '.join(submodules)}"
        )

    if destination.exists() and any(destination.iterdir()):
        raise PreflightError(
            f"isolated provider destination is not empty: {destination}"
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    clone = subprocess.run(
        [
            "git",
            "clone",
            "--quiet",
            "--no-checkout",
            "--no-local",
            str(provider_repo),
            str(destination),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if clone.returncode != 0:
        detail = clone.stderr.strip() or "clone failed"
        raise PreflightError(
            "cannot create isolated Stable Retro Turbo provider checkout: "
            f"{detail}"
        )
    checkout = subprocess.run(
        ["git", "-C", str(destination), "checkout", "--quiet", "--detach", revision],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "GIT_NO_REPLACE_OBJECTS": "1"},
    )
    if checkout.returncode != 0:
        detail = checkout.stderr.strip() or "checkout failed"
        raise PreflightError(
            "cannot checkout pinned Stable Retro Turbo provider revision: "
            f"{detail}"
        )
    return destination.resolve()


def preflight(
    provider_repo: Path,
    data_root: Path | None,
    *,
    prepare_provider: Path | None = None,
) -> OracleInputs:
    pin = ProviderPin.load()
    if data_root is None:
        raise PreflightError(
            "RETRO_DATA_PATH is required and must point to separately obtained "
            "lawful Stable Retro integration data"
        )
    data_dir = data_root.expanduser().resolve() / "stable" / GAME
    missing = [name for name in REQUIRED_DATA_FILES if not (data_dir / name).is_file()]
    if missing:
        raise PreflightError(
            "lawful Breakout oracle data is incomplete at "
            f"{data_dir}; missing: {', '.join(missing)}"
        )

    provider_repo = provider_repo.expanduser().resolve()
    if not provider_repo.is_dir():
        raise PreflightError(
            f"pinned Stable Retro Turbo provider checkout not found at "
            f"{provider_repo}; expected a Git checkout"
        )

    actual_revision = _git_head(provider_repo)
    if actual_revision != pin.revision:
        raise PreflightError(
            "Stable Retro Turbo provider revision is incompatible: "
            f"expected {pin.revision}, found {actual_revision} at {provider_repo}"
        )
    if prepare_provider is not None:
        provider_repo = _prepare_provider_checkout(
            provider_repo,
            prepare_provider.expanduser().resolve(),
            revision=pin.revision,
        )

    package_dir = provider_repo / pin.module
    if not package_dir.is_dir():
        raise PreflightError(
            f"pinned Stable Retro Turbo provider checkout not found at "
            f"{provider_repo}; expected module directory {package_dir}"
        )

    version_path = package_dir / "VERSION.txt"
    try:
        actual_version = version_path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise PreflightError(
            f"cannot read Stable Retro Turbo provider version at {version_path}: {error}"
        ) from error
    if actual_version != pin.version:
        raise PreflightError(
            "Stable Retro Turbo provider version is incompatible: "
            f"expected {pin.version}, found {actual_version or '<empty>'}"
        )

    provider_data_dir = package_dir / "data" / "stable" / GAME
    missing_provider_files = [
        name
        for name in REQUIRED_PROVIDER_INTEGRATION_FILES
        if not (provider_data_dir / name).is_file()
    ]
    if missing_provider_files:
        raise PreflightError(
            "pinned Stable Retro Turbo integration is incomplete at "
            f"{provider_data_dir}; missing: {', '.join(missing_provider_files)}"
        )

    return OracleInputs(
        pin=pin,
        provider_repo=provider_repo,
        data_dir=data_dir,
        provider_data_dir=provider_data_dir,
    )


def _load_provider(inputs: OracleInputs):
    try:
        provider = importlib.import_module(inputs.pin.module)
    except (ImportError, OSError) as error:
        raise PreflightError(
            "pinned Stable Retro Turbo provider cannot be imported; install the "
            f"checkout at {inputs.provider_repo} into this Python environment: {error}"
        ) from error

    module_path = Path(provider.__file__).resolve()
    direct_url_text = importlib.metadata.distribution(
        inputs.pin.distribution
    ).read_text("direct_url.json")
    direct_url = json.loads(direct_url_text) if direct_url_text else {}
    parsed_url = urlparse(direct_url.get("url", ""))
    installed_source = (
        Path(unquote(parsed_url.path)).resolve()
        if parsed_url.scheme == "file"
        else None
    )
    if not module_path.is_relative_to(inputs.provider_repo) and (
        installed_source != inputs.provider_repo
    ):
        raise PreflightError(
            "Stable Retro Turbo was not installed from the pinned checkout: "
            f"module={module_path}, source={installed_source}"
        )
    if provider.__version__ != inputs.pin.version:
        raise PreflightError(
            "imported Stable Retro Turbo version is incompatible: "
            f"expected {inputs.pin.version}, found {provider.__version__}"
        )
    metadata = provider.RetroVecEnv.metadata
    api_version = metadata.get("turbo_api_version")
    transport = metadata.get("transition_transport")
    if api_version != inputs.pin.turbo_api_version or transport != "numpy":
        raise PreflightError(
            "Stable Retro Turbo public vector API is incompatible: "
            f"expected Turbo API {inputs.pin.turbo_api_version} with NumPy "
            f"transport, found API {api_version!r} with {transport!r} transport"
        )
    return provider


def _oracle_info_file(data_dir: Path, directory: Path) -> Path:
    try:
        payload = json.loads((data_dir / "data.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PreflightError(f"cannot read Breakout oracle information: {error}") from error
    payload.setdefault("info", {})["ball_y"] = {"address": 229, "type": "|u1"}
    path = directory / "oracle-data.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _make_environments(
    inputs: OracleInputs,
    provider,
    info_path: Path,
    *,
    noop_reset_max: int,
):
    from env_breakoutatari2600_turbo_native import BreakoutVecEnv

    common = {
        "use_restricted_actions": ACTION_TABLE,
        "render_mode": "rgb_array",
        "num_envs": 2,
        "num_threads": 1,
        "obs_copy": "copy",
        "obs_resize": (84, 84),
        "obs_crop": (17, 0, 0, 0),
        "obs_crop_mode": "mask",
        "obs_crop_fill": 0,
        "obs_grayscale": True,
        "obs_resize_algorithm": "area",
        "obs_layout": "chw",
        "frame_skip": 4,
        "frame_stack": 4,
        "maxpool_last_two": False,
        "noop_reset_max": noop_reset_max,
        "use_fire_reset": False,
        "sticky_action_prob": 0.0,
        "reward_clip": False,
        "info_filter": "all",
    }
    oracle = provider.RetroVecEnv(
        GAME,
        state=str(inputs.provider_data_dir / "Start.state"),
        scenario=str(inputs.provider_data_dir / "scenario.json"),
        info=str(info_path),
        rom_path=str(inputs.data_dir / "rom.a26"),
        **common,
    )
    try:
        native = BreakoutVecEnv(
            GAME,
            state="Start",
            scenario="scenario",
            info="data",
            **common,
        )
    except Exception:
        oracle.close()
        raise
    return oracle, native


def _equal(field: str, oracle_value, native_value, *, context: str) -> None:
    left = np.asarray(oracle_value)
    right = np.asarray(native_value)
    if left.shape != right.shape or left.dtype != right.dtype or not np.array_equal(
        left, right
    ):
        samples: list[dict[str, object]] = []
        if left.shape == right.shape:
            for raw_index in np.argwhere(left != right)[:8]:
                index = tuple(int(value) for value in raw_index)
                samples.append(
                    {
                        "index": index,
                        "oracle": np.asarray(left[index]).item(),
                        "native": np.asarray(right[index]).item(),
                    }
                )
        differing = (
            int(np.count_nonzero(left != right))
            if left.shape == right.shape
            else "shape mismatch"
        )
        raise ObservableMismatch(
            f"{context}: {field} mismatch; oracle shape/dtype={left.shape}/{left.dtype}, "
            f"native shape/dtype={right.shape}/{right.dtype}, differing={differing}, "
            f"samples={samples}"
        )


def _compare_infos(
    oracle_info: dict,
    native_info: dict,
    *,
    context: str,
    include_reset_fields: bool,
) -> None:
    shared = set(oracle_info) & set(native_info)
    required = set(REQUIRED_SHARED_INFO)
    if include_reset_fields:
        required.update({"state_index", "start_source", "noop_reset_count"})
    missing = sorted(required - shared)
    if missing:
        raise ObservableMismatch(
            f"{context}: shared information is incomplete; missing {missing}"
        )
    for key in sorted(shared):
        if key.startswith("_"):
            _equal(
                f"info[{key!r}]", oracle_info[key], native_info[key], context=context
            )
            continue
        mask_key = f"_{key}"
        if mask_key in shared:
            mask = np.asarray(oracle_info[mask_key], dtype=np.bool_)
            oracle_value = np.asarray(oracle_info[key])[mask]
            native_value = np.asarray(native_info[key])[mask]
        else:
            oracle_value = oracle_info[key]
            native_value = native_info[key]
        _equal(
            f"info[{key!r}]", oracle_value, native_value, context=context
        )


def _compare_reset(
    oracle,
    native,
    *,
    seed,
    context: str,
    options: dict | None = None,
):
    oracle_observation, oracle_info = oracle.reset(seed=seed, options=options)
    native_observation, native_info = native.reset(seed=seed, options=options)
    _compare_reset_values(
        oracle,
        native,
        oracle_observation,
        native_observation,
        oracle_info,
        native_info,
        context=context,
    )
    return oracle_info


def _compare_reset_values(
    oracle,
    native,
    oracle_observation,
    native_observation,
    oracle_info: dict,
    native_info: dict,
    *,
    context: str,
) -> None:
    _equal("policy observation", oracle_observation, native_observation, context=context)
    for lane in range(oracle.num_envs):
        _equal(
            f"rendered frame lane {lane}",
            canonicalize_provider_frame(oracle.render_lane(lane)),
            native.render_lane(lane),
            context=context,
        )
    _compare_infos(
        oracle_info,
        native_info,
        context=context,
        include_reset_fields=True,
    )


def _seed_for_noop_count(count: int, maximum: int) -> int:
    for seed in range(100_000):
        sampled = int(
            np.random.default_rng(seed).integers(
                1, maximum + 1, dtype=np.uint64
            )
        )
        if sampled == count:
            return seed
    raise RuntimeError(f"could not align reset noop count {count}")


def sample_noop_reset_distribution(
    environment, *, seeds: tuple[int, ...], maximum: int
) -> tuple[np.ndarray, dict[int, tuple[int, ...]]]:
    lane_count = int(environment.num_envs)
    if lane_count <= 0 or not seeds:
        raise ValueError("reset distribution requires lanes and a seed corpus")
    counts = np.empty(len(seeds) * lane_count, dtype=np.int64)
    representative_seeds: dict[int, tuple[int, ...]] = {}
    for index, seed in enumerate(seeds):
        seed_batch = (seed,) * lane_count
        _, info = environment.reset(seed=list(seed_batch))
        lane_counts = np.asarray(info["noop_reset_count"], dtype=np.int64)
        if lane_counts.shape != (lane_count,):
            raise ObservableMismatch(
                "seeded reset distribution has incompatible noop_reset_count "
                f"shape {lane_counts.shape}; expected ({lane_count},)"
            )
        offset = index * lane_count
        counts[offset : offset + lane_count] = lane_counts
        for count in lane_counts:
            representative_seeds.setdefault(int(count), seed_batch)
    if np.any((counts < 1) | (counts > maximum)):
        raise ObservableMismatch(
            f"seeded reset distribution sampled outside inclusive 1..{maximum}: "
            f"{counts.tolist()}"
        )
    return counts, representative_seeds


def validate_seeded_reset_semantics(
    oracle,
    native,
    *,
    representative_seeds: dict[int, tuple[int, ...]],
    maximum: int,
) -> np.ndarray:
    expected_counts = set(range(1, maximum + 1))
    missing = sorted(expected_counts - set(representative_seeds))
    if missing:
        raise ObservableMismatch(
            "seeded reset semantics corpus did not observe noop counts "
            f"{missing} from inclusive 1..{maximum}"
        )

    verified: list[int] = []
    for target_count in sorted(expected_counts):
        oracle_seeds = representative_seeds[target_count]
        oracle_observation, oracle_info = oracle.reset(seed=list(oracle_seeds))
        oracle_counts = np.asarray(
            oracle_info["noop_reset_count"], dtype=np.int64
        )
        if target_count not in oracle_counts:
            raise ObservableMismatch(
                f"seeded reset noop count {target_count}: oracle seed corpus "
                f"was not reproducible; observed {oracle_counts.tolist()}"
            )
        aligned_native_seeds = [
            _seed_for_noop_count(int(count), maximum) for count in oracle_counts
        ]
        native_observation, native_info = native.reset(seed=aligned_native_seeds)
        _compare_reset_values(
            oracle,
            native,
            oracle_observation,
            native_observation,
            oracle_info,
            native_info,
            context=f"seeded reset noop count {target_count}",
        )
        verified.append(target_count)
    return np.asarray(verified, dtype=np.int64)


def validate_noop_reset_distribution(
    oracle_counts: np.ndarray,
    native_counts: np.ndarray,
    *,
    maximum: int,
) -> dict[str, object]:
    """Compare reproducible empirical reset distributions without pairing seeds."""
    oracle = np.asarray(oracle_counts, dtype=np.int64).reshape(-1)
    native = np.asarray(native_counts, dtype=np.int64).reshape(-1)
    if oracle.shape != native.shape or oracle.size < 32:
        raise ValueError("reset distributions require equal samples of at least 32")
    for name, counts in (("oracle", oracle), ("native", native)):
        if np.any((counts < 1) | (counts > maximum)):
            raise ObservableMismatch(
                f"{name} reset distribution sampled outside inclusive 1..{maximum}: "
                f"{counts.tolist()}"
            )

    oracle_histogram = np.bincount(oracle, minlength=maximum + 1)[1:]
    native_histogram = np.bincount(native, minlength=maximum + 1)[1:]
    oracle_cdf = np.cumsum(oracle_histogram, dtype=np.float64) / oracle.size
    native_cdf = np.cumsum(native_histogram, dtype=np.float64) / native.size
    cdf_distance = float(np.max(np.abs(oracle_cdf - native_cdf)))
    if cdf_distance > MAX_RESET_CDF_DISTANCE:
        raise ObservableMismatch(
            "seeded reset distribution mismatch: "
            f"empirical CDF distance {cdf_distance:.6f} exceeds "
            f"{MAX_RESET_CDF_DISTANCE:.6f}; "
            f"oracle_histogram={oracle_histogram.tolist()}, "
            f"native_histogram={native_histogram.tolist()}"
        )
    return {
        "matches": True,
        "sample_count": int(oracle.size),
        "seed_corpus": [RESET_DISTRIBUTION_SEEDS[0], RESET_DISTRIBUTION_SEEDS[-1]],
        "maximum": maximum,
        "cdf_distance": cdf_distance,
        "maximum_cdf_distance": MAX_RESET_CDF_DISTANCE,
        "oracle_histogram": oracle_histogram.astype(int).tolist(),
        "native_histogram": native_histogram.astype(int).tolist(),
    }


def _compare_step(oracle, native, actions: np.ndarray, *, context: str):
    oracle_result = oracle.step(actions)
    native_result = native.step(actions)
    for lane in range(oracle.num_envs):
        _equal(
            f"rendered frame lane {lane}",
            canonicalize_provider_frame(oracle.render_lane(lane)),
            native.render_lane(lane),
            context=context,
        )
    labels = (
        "policy observation",
        "reward",
        "termination",
        "truncation",
    )
    for label, oracle_value, native_value in zip(
        labels, oracle_result[:4], native_result[:4], strict=True
    ):
        _equal(label, oracle_value, native_value, context=context)
    _compare_infos(
        oracle_result[4],
        native_result[4],
        context=context,
        include_reset_fields=False,
    )
    return oracle_result


def _trajectory(
    oracle,
    native,
    *,
    name: str,
    steps: int,
    random_actions: bool,
) -> dict[str, object]:
    info = _compare_reset(
        oracle,
        native,
        seed=[101, 202],
        context=f"{name} reset",
    )
    rng = np.random.default_rng(87123)
    completed = np.zeros(2, dtype=np.int64)
    executed = 0
    cycle = np.asarray(
        ((0, 0), (2, 3), (2, 3), (0, 0), (3, 2), (3, 2)), dtype=np.int64
    )
    for step in range(steps):
        executed = step + 1
        if random_actions:
            actions = rng.integers(0, 4, size=2, dtype=np.int64)
        else:
            actions = cycle[step % len(cycle)].copy()
        inactive = np.asarray(info["ball_y"]) == 0
        actions[inactive] = 1
        result = _compare_step(
            oracle,
            native,
            actions,
            context=f"{name} step {step + 1}",
        )
        info = result[4]
        done = np.asarray(result[2]) | np.asarray(result[3])
        if np.any(done):
            completed += done.astype(np.int64)
            break
    return {
        "exact": True,
        "steps": executed,
        "maximum_steps": steps,
        "completed_episodes": completed.astype(int).tolist(),
    }


def run_live_suite(inputs: OracleInputs, *, steps: int) -> dict[str, object]:
    if steps <= 0:
        raise ValueError("steps must be positive")
    provider = _load_provider(inputs)
    report: dict[str, object] = {
        "provider": {
            "distribution": inputs.pin.distribution,
            "module": inputs.pin.module,
            "version": provider.__version__,
            "revision": inputs.pin.revision,
            "turbo_api_version": provider.RetroVecEnv.metadata[
                "turbo_api_version"
            ],
        }
    }
    with tempfile.TemporaryDirectory(prefix="breakout-turbo-oracle-") as temporary:
        info_path = _oracle_info_file(inputs.provider_data_dir, Path(temporary))

        oracle, native = _make_environments(
            inputs, provider, info_path, noop_reset_max=0
        )
        try:
            _compare_reset(
                oracle,
                native,
                seed=[11, 29],
                context="aligned reset",
            )
            report["aligned_reset"] = {"exact": True}
            report["trajectories"] = {
                "cycling": _trajectory(
                    oracle,
                    native,
                    name="cycling",
                    steps=steps,
                    random_actions=False,
                ),
                "seeded-random": _trajectory(
                    oracle,
                    native,
                    name="seeded-random",
                    steps=steps,
                    random_actions=True,
                ),
            }
        finally:
            oracle.close()
            native.close()

        oracle, native = _make_environments(
            inputs, provider, info_path, noop_reset_max=30
        )
        try:
            oracle_distribution, representative_seeds = (
                sample_noop_reset_distribution(
                    oracle,
                    seeds=RESET_DISTRIBUTION_SEEDS,
                    maximum=30,
                )
            )
            native_distribution, _ = sample_noop_reset_distribution(
                native,
                seeds=RESET_DISTRIBUTION_SEEDS,
                maximum=30,
            )
            distribution = validate_noop_reset_distribution(
                oracle_distribution,
                native_distribution,
                maximum=30,
            )
            counts = validate_seeded_reset_semantics(
                oracle,
                native,
                representative_seeds=representative_seeds,
                maximum=30,
            )
            report["seeded_reset_noops"] = {
                "exact": True,
                "counts": counts.astype(int).tolist(),
                "distribution": distribution,
            }
        finally:
            oracle.close()
            native.close()
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--provider-repo",
        type=Path,
        default=REPO_ROOT.parent / "env-StableRetro-turbo",
        help="checkout of the pinned Stable Retro Turbo provider",
    )
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path(os.environ["RETRO_DATA_PATH"])
        if os.environ.get("RETRO_DATA_PATH")
        else None,
        help="lawful Stable Retro data root (defaults to RETRO_DATA_PATH)",
    )
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate the provider pin and lawful data without loading either environment",
    )
    parser.add_argument(
        "--prepare-provider",
        type=Path,
        help="create and validate an isolated checkout of the pinned provider commit",
    )
    parser.add_argument(
        "--steps",
        type=int,
        default=2_048,
        help="maximum steps per representative canonical episode",
    )
    parser.add_argument("--json", action="store_true", help="emit the exact report as JSON")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        inputs = preflight(
            args.provider_repo,
            args.data_root,
            prepare_provider=args.prepare_provider,
        )
    except PreflightError as error:
        print(f"oracle validation unavailable: {error}", file=sys.stderr)
        return 2
    if args.preflight_only or args.prepare_provider is not None:
        print(
            "Stable Retro Turbo oracle inputs validated from isolated source: "
            f"{inputs.pin.version} at {inputs.pin.revision} ({inputs.provider_repo})"
        )
        return 0
    try:
        report = run_live_suite(inputs, steps=args.steps)
    except PreflightError as error:
        print(f"oracle validation unavailable: {error}", file=sys.stderr)
        return 2
    except ObservableMismatch as error:
        print(f"oracle mismatch: {error}", file=sys.stderr)
        return 1
    except (ImportError, OSError, RuntimeError, ValueError) as error:
        print(f"oracle validation incompatible: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        provider = report["provider"]
        print(
            "Stable Retro Turbo oracle exact: "
            f"{provider['version']} at {provider['revision']}"
        )
        for name, trajectory in report["trajectories"].items():
            print(
                f"  {name}: {trajectory['steps']} steps, "
                f"completed episodes {trajectory['completed_episodes']}"
            )
        counts = report["seeded_reset_noops"]["counts"]
        print(f"  seeded reset noops: {counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
