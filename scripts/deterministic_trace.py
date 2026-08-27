#!/usr/bin/env python3
"""Generate and compare ROM-free deterministic public lane traces."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import platform as host_platform
import sys
from collections.abc import Mapping, Sequence
from importlib.metadata import version
from pathlib import Path
from typing import Any

import numpy as np
from env_breakoutatari2600_turbo_native import BreakoutVecEnv

GAME_ID = "Breakout-Atari2600-v0"
SCHEMA_VERSION = 2
WORKLOAD_ID = "public-lane-determinism-v2"
STEP_COUNT = 96
SNAPSHOT_STEP = 40
SUPPORTED_PLATFORMS = ("macos-arm64", "linux-x86_64")


class TraceMismatch(RuntimeError):
    """A deterministic trace differs at a public value."""


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def trace_digest(trace: Sequence[Mapping[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(trace).encode()).hexdigest()


def _array_value(value: np.ndarray) -> dict[str, Any]:
    contiguous = np.ascontiguousarray(value)
    data = contiguous.tobytes()
    return {
        "dtype": contiguous.dtype.str,
        "shape": list(contiguous.shape),
        "sha256": hashlib.sha256(data).hexdigest(),
        "data_base64": base64.b64encode(data).decode("ascii"),
    }


def _scalar_value(value: Any) -> bool | int | str:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (float, np.floating)):
        return float(value).hex()
    if isinstance(value, (int, np.integer)):
        return int(value)
    raise TypeError(f"unsupported public scalar type: {type(value).__name__}")


def _infos_for_lane(infos: Mapping[str, np.ndarray], lane: int) -> dict[str, Any]:
    return {key: _scalar_value(infos[key][lane]) for key in sorted(infos)}


def _reset_record(
    observation: np.ndarray, infos: Mapping[str, np.ndarray], lane: int
) -> dict[str, Any]:
    return {
        "kind": "reset",
        "observation": _array_value(observation[lane]),
        "infos": _infos_for_lane(infos, lane),
    }


def _transition_record(
    transition: tuple[
        np.ndarray,
        np.ndarray,
        np.ndarray,
        np.ndarray,
        Mapping[str, np.ndarray],
    ],
    lane: int,
    step: int,
) -> dict[str, Any]:
    observations, rewards, terminated, truncated, infos = transition
    return {
        "kind": "transition",
        "step": step,
        "observation": _array_value(observations[lane]),
        "reward": _scalar_value(rewards[lane]),
        "terminated": _scalar_value(terminated[lane]),
        "truncated": _scalar_value(truncated[lane]),
        "infos": _infos_for_lane(infos, lane),
    }


def _target_action(step: int) -> int:
    if step == 0 or step % 31 == 0:
        return 1
    return (0, 2, 2, 0, 3, 3)[(step // 5) % 6]


def _neighbor_action(step: int, logical_lane: int) -> int:
    if step == logical_lane:
        return 1
    return (0, 2, 3, 2, 0, 3)[(step + logical_lane * 7) % 6]


def _actions(
    step: int, logical_lanes: tuple[int, ...], *, active_neighbors: bool
) -> np.ndarray:
    values = np.zeros(len(logical_lanes), dtype=np.uint8)
    for physical_lane, logical_lane in enumerate(logical_lanes):
        if logical_lane == 0:
            values[physical_lane] = _target_action(step)
        elif active_neighbors:
            values[physical_lane] = _neighbor_action(step, logical_lane)
    return values


def _first_difference(left: Any, right: Any, path: str = "trace"):
    if type(left) is not type(right):
        return path, left, right
    if isinstance(left, Mapping):
        if _is_array_value(left) and _is_array_value(right):
            return _array_difference(left, right, path)
        left_keys = sorted(left)
        right_keys = sorted(right)
        if left_keys != right_keys:
            return f"{path}.keys", left_keys, right_keys
        for key in left_keys:
            difference = _first_difference(left[key], right[key], f"{path}.{key}")
            if difference is not None:
                return difference
        return None
    if isinstance(left, list):
        if len(left) != len(right):
            return f"{path}.length", len(left), len(right)
        for index, (left_value, right_value) in enumerate(
            zip(left, right, strict=True)
        ):
            difference = _first_difference(
                left_value, right_value, f"{path}[{index}]"
            )
            if difference is not None:
                return difference
        return None
    if left != right:
        return path, left, right
    return None


def _is_array_value(value: Mapping[str, Any]) -> bool:
    return set(value) == {"dtype", "shape", "sha256", "data_base64"}


def _array_difference(
    left: Mapping[str, Any], right: Mapping[str, Any], path: str
):
    for key in ("dtype", "shape"):
        if left[key] != right[key]:
            return f"{path}.{key}", left[key], right[key]
    dtype = np.dtype(left["dtype"])
    if dtype != np.dtype(np.uint8):
        return f"{path}.dtype", left["dtype"], "uint8 policy observation"
    left_data = base64.b64decode(left["data_base64"], validate=True)
    right_data = base64.b64decode(right["data_base64"], validate=True)
    expected_size = int(np.prod(left["shape"], dtype=np.int64))
    if len(left_data) != expected_size or len(right_data) != expected_size:
        return (
            f"{path}.data_base64.length",
            len(left_data),
            len(right_data),
        )
    left_array = np.frombuffer(left_data, dtype=dtype).reshape(left["shape"])
    right_array = np.frombuffer(right_data, dtype=dtype).reshape(right["shape"])
    different = np.argwhere(left_array != right_array)
    if different.size:
        coordinates = tuple(int(value) for value in different[0])
        coordinate_path = ",".join(str(value) for value in coordinates)
        return (
            f"{path}[{coordinate_path}]",
            int(left_array[coordinates]),
            int(right_array[coordinates]),
        )
    if left["sha256"] != right["sha256"]:
        return f"{path}.sha256", left["sha256"], right["sha256"]
    return None


def _format_difference(difference: tuple[str, Any, Any]) -> str:
    path, left, right = difference
    return f"{path}: {left!r} != {right!r}"


def _run_shape(
    *,
    logical_lanes: tuple[int, ...],
    num_threads: int,
    active_neighbors: bool,
) -> tuple[list[dict[str, Any]], bool]:
    target_lane = logical_lanes.index(0)
    configuration = {
        "num_envs": len(logical_lanes),
        "num_threads": num_threads,
        "frame_skip": 4,
        "frame_stack": 4,
        "noop_reset_max": 7,
        "info_filter": "all",
    }
    env = BreakoutVecEnv(GAME_ID, **configuration)
    restored = BreakoutVecEnv(GAME_ID, **configuration)
    try:
        seeds = [20260827 + logical_lane * 101 for logical_lane in logical_lanes]
        starts = np.asarray(
            [logical_lane % 4 for logical_lane in logical_lanes], dtype=np.int32
        )
        observation, infos = env.reset(seed=seeds, options={"state_indices": starts})
        trace = [_reset_record(observation, infos, target_lane)]
        snapshot_states: list[bytes] | None = None
        for step in range(STEP_COUNT):
            if step == SNAPSHOT_STEP:
                snapshot_states = env.get_state()
            transition = env.step(
                _actions(step, logical_lanes, active_neighbors=active_neighbors)
            )
            trace.append(_transition_record(transition, target_lane, step))

        assert snapshot_states is not None
        restored.reset(seed=seeds, options={"state_indices": starts})
        restored.set_state(snapshot_states)
        replay: list[dict[str, Any]] = []
        for step in range(SNAPSHOT_STEP, STEP_COUNT):
            transition = restored.step(
                _actions(step, logical_lanes, active_neighbors=active_neighbors)
            )
            replay.append(_transition_record(transition, target_lane, step))
        expected = trace[SNAPSHOT_STEP + 1 :]
        difference = _first_difference(expected, replay)
        if difference is not None:
            raise TraceMismatch(
                "serialized snapshot continuation diverged at "
                + _format_difference(difference)
            )
        return trace, True
    finally:
        env.close()
        restored.close()


def generate_trace(platform_name: str) -> dict[str, Any]:
    shapes = {
        "scalar": {
            "logical_lanes": (0,),
            "num_threads": 1,
            "active_neighbors": False,
        },
        "batch": {
            "logical_lanes": (0, 1, 2, 3),
            "num_threads": 1,
            "active_neighbors": False,
        },
        "active_neighbors": {
            "logical_lanes": (0, 1, 2, 3),
            "num_threads": 1,
            "active_neighbors": True,
        },
        "reordered_lanes": {
            "logical_lanes": (1, 2, 3, 0),
            "num_threads": 1,
            "active_neighbors": True,
        },
        "parallel_threads": {
            "logical_lanes": (1, 2, 3, 0),
            "num_threads": 4,
            "active_neighbors": True,
        },
    }
    traces: dict[str, list[dict[str, Any]]] = {}
    snapshot_results: dict[str, bool] = {}
    for name, configuration in shapes.items():
        traces[name], snapshot_results[name] = _run_shape(**configuration)

    baseline = traces["scalar"]
    for name, trace in traces.items():
        difference = _first_difference(baseline, trace)
        if difference is not None:
            raise TraceMismatch(
                f"execution shape {name!r} diverged from 'scalar' at "
                + _format_difference(difference)
            )

    digest = trace_digest(baseline)
    return {
        "schema_version": SCHEMA_VERSION,
        "workload": WORKLOAD_ID,
        "package_version": version("env-breakoutatari2600-turbo-native"),
        "platform": platform_name,
        "coverage": [
            "transitions",
            "observations",
            "rewards",
            "lifecycle_flags",
            "shared_information",
            "serialized_snapshot_continuation",
        ],
        "shape_digests": {name: trace_digest(trace) for name, trace in traces.items()},
        "snapshot_continuation": {
            "kind": "serialized",
            "from_step": SNAPSHOT_STEP,
            "verified": all(snapshot_results.values()),
        },
        "trace_digest": digest,
        "trace": baseline,
    }


def detect_supported_platform() -> str:
    machine = host_platform.machine().lower()
    if sys.platform == "darwin" and machine in {"arm64", "aarch64"}:
        return "macos-arm64"
    if sys.platform.startswith("linux") and machine in {"x86_64", "amd64"}:
        return "linux-x86_64"
    raise RuntimeError(
        f"unsupported trace platform: sys.platform={sys.platform!r}, machine={machine!r}"
    )


def compare_trace_files(paths: Sequence[Path]) -> None:
    manifests = [json.loads(Path(path).read_text(encoding="utf-8")) for path in paths]
    by_platform = {manifest.get("platform"): manifest for manifest in manifests}
    if set(by_platform) != set(SUPPORTED_PLATFORMS) or len(manifests) != 2:
        raise TraceMismatch(
            "expected fresh traces for macos-arm64 and linux-x86_64; got "
            + repr(sorted(str(value) for value in by_platform))
        )
    macos = by_platform["macos-arm64"]
    linux = by_platform["linux-x86_64"]
    for key in ("schema_version", "workload", "package_version", "coverage"):
        if macos.get(key) != linux.get(key):
            raise TraceMismatch(
                f"macos-arm64 and linux-x86_64 differ at {key}: "
                f"{macos.get(key)!r} != {linux.get(key)!r}"
            )
    difference = _first_difference(macos.get("trace"), linux.get("trace"))
    if difference is not None:
        raise TraceMismatch(
            "macos-arm64 and linux-x86_64 first diverge at "
            + _format_difference(difference)
        )
    if macos.get("trace_digest") != trace_digest(macos["trace"]):
        raise TraceMismatch("macos-arm64 trace_digest does not match its public trace")
    if linux.get("trace_digest") != trace_digest(linux["trace"]):
        raise TraceMismatch("linux-x86_64 trace_digest does not match its public trace")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    generate = subparsers.add_parser("generate", help="generate a fresh public trace")
    generate.add_argument("--output", type=Path, required=True)
    compare = subparsers.add_parser("compare", help="compare supported-platform traces")
    compare.add_argument("traces", type=Path, nargs="+")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "generate":
            manifest = generate_trace(detect_supported_platform())
            args.output.write_text(
                json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            print(
                f"{manifest['platform']} {manifest['trace_digest']} "
                f"({args.output})"
            )
        else:
            compare_trace_files(args.traces)
            print("macos-arm64 and linux-x86_64 public traces are bit-identical")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"deterministic trace failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
