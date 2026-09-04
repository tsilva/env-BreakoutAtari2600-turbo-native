from __future__ import annotations

import copy
import operator
from collections.abc import Mapping, Sequence
from types import MappingProxyType
from typing import Any, Literal

import gymnasium as gym
import numpy as np
from gymnasium.vector import AutoresetMode, VectorEnv

from ._env_breakoutatari2600_turbo_native import (
    FIXED_POINT_ONE,
    RAW_HEIGHT,
    RAW_WIDTH,
    RENDER_HEIGHT,
    RENDER_WIDTH,
    NativeBreakoutVecEnv,
)
from ._env_breakoutatari2600_turbo_native import (
    NATIVE_SIGNAL_NAMES as _NATIVE_EXTENSION_SIGNAL_NAMES,
)
from .action_tables import ACTION_TABLES, BUTTONS, ActionTable, resolve_custom_action

_STABLE_SIGNAL_NAMES = (
    "paddle_x",
    "ball_x",
    "ball_y",
    "ball_vx",
    "ball_vy",
    "brick_mask",
    "brick_mask_high",
    "score",
    "lives",
    "tick",
    "bricks_remaining",
    "walls_cleared",
    "layout_id",
    "collision_events",
    "pending_reset",
)
_NATIVE_SIGNAL_NAMES = tuple(_NATIVE_EXTENSION_SIGNAL_NAMES)
_NATIVE_SIGNAL_INDEX = {name: index for index, name in enumerate(_NATIVE_SIGNAL_NAMES)}
POLICY_INFO_KEYS = (
    "paddle_x",
    "paddle_x_normalized",
    "ball_x",
    "ball_x_normalized",
    "ball_y",
    "ball_y_normalized",
    "ball_screen_y",
    "ball_screen_y_normalized",
    "ball_vx",
    "ball_vx_normalized",
    "ball_vy",
    "ball_vy_normalized",
    "paddle_width",
    "paddle_width_normalized",
    "ball_paddle_offset",
    "ball_paddle_offset_normalized",
    "score",
    "score_normalized",
    "lives",
    "lives_normalized",
    "bricks_remaining",
    "bricks_remaining_normalized",
    "walls_cleared",
    "walls_cleared_normalized",
    "brick_grid",
    "serve_phase",
)
_NORMALIZED_SOURCES = {
    "paddle_x_normalized": ("paddle_x", FIXED_POINT_ONE * RAW_WIDTH),
    "ball_x_normalized": ("ball_x", FIXED_POINT_ONE * RAW_WIDTH),
    "ball_y_normalized": ("ball_y", 255),
    "ball_screen_y_normalized": (
        "ball_screen_y",
        FIXED_POINT_ONE * RAW_HEIGHT,
    ),
    "ball_vx_normalized": ("ball_vx", 2 * FIXED_POINT_ONE),
    "ball_vy_normalized": ("ball_vy", 27 * FIXED_POINT_ONE // 8),
    "paddle_width_normalized": ("paddle_width", 16),
    "ball_paddle_offset_normalized": (
        "ball_paddle_offset",
        FIXED_POINT_ONE * RAW_WIDTH,
    ),
    "lives_normalized": ("lives", 5),
    "walls_cleared_normalized": ("walls_cleared", 2),
}
_DYNAMIC_NORMALIZED_SOURCES = {
    "score_normalized": ("score", "_layout_max_score"),
    "bricks_remaining_normalized": (
        "bricks_remaining",
        "_layout_initial_bricks",
    ),
}
_AUXILIARY_INFO_KEYS = tuple(
    key for key in POLICY_INFO_KEYS if key not in _STABLE_SIGNAL_NAMES
)
_AVAILABLE_INFO_KEYS = (*_STABLE_SIGNAL_NAMES, *_AUXILIARY_INFO_KEYS)
_CANONICAL_GAME = "Breakout-Atari2600-v0"
_START_IDS = ("Start", "checker", "tunnel", "sparse")
_RETRO_BUTTON_COUNT = 8
_FILTERED_ACTION_ROWS = (
    (0, 0, 0, 0, 0, 0, 0, 0),
    (1, 0, 0, 0, 0, 0, 0, 0),
    (0, 0, 0, 0, 0, 0, 0, 1),
    (0, 0, 0, 0, 0, 0, 1, 0),
)
_NATIVE_ACTION_BY_MASK = {
    0: 0,
    1 << BUTTONS.index("BUTTON"): 1,
    1 << BUTTONS.index("RIGHT"): 2,
    1 << BUTTONS.index("LEFT"): 3,
}
_ATARI_2600_NTSC_PALETTE = np.array(
    [
        [0, 0, 0],
        [136, 136, 136],
        [200, 72, 72],
        [192, 104, 56],
        [176, 120, 48],
        [160, 160, 40],
        [72, 160, 72],
        [64, 72, 200],
        [64, 152, 128],
    ],
    dtype=np.uint8,
)


def _signal_spec(key: str) -> dict[str, Any]:
    dtype = "int64"
    shape: tuple[int, ...] = ()
    units = "count"
    normalization: str | None = None
    nominal_range: tuple[float | int, float | int] | None = None
    source = "stable" if key in _STABLE_SIGNAL_NAMES else "auxiliary"

    if key in _NORMALIZED_SOURCES:
        raw, divisor = _NORMALIZED_SOURCES[key]
        dtype = "float32"
        units = "ratio"
        normalization = f"{raw} / {divisor}; not clipped"
        nominal_range = (
            (-1.0, 1.0)
            if raw
            in {
                "ball_vx",
                "ball_vy",
                "ball_paddle_offset",
            }
            else (0.0, 1.0)
        )
    elif key in _DYNAMIC_NORMALIZED_SOURCES:
        raw, divisor = _DYNAMIC_NORMALIZED_SOURCES[key]
        dtype = "float32"
        units = "ratio"
        normalization = f"{raw} / layout-specific {divisor}; not clipped"
        nominal_range = (0.0, 1.0)
    elif key == "brick_grid":
        dtype = "uint8"
        shape = (6, 18)
        units = "occupied"
        nominal_range = (0, 1)
    elif key == "serve_phase":
        dtype = "int8"
        units = "phase"
        nominal_range = (-1, 3)
    elif key in {
        "paddle_x",
        "ball_x",
        "ball_screen_y",
        "ball_vx",
        "ball_vy",
        "ball_paddle_offset",
    }:
        units = "fixed_point_pixels"
    elif key == "ball_y":
        units = "atari_ram_coordinate"
        nominal_range = (0, 255)
    elif key == "paddle_width":
        units = "pixels"
        nominal_range = (12, 16)

    return {
        "dtype": dtype,
        "shape": shape,
        "units": units,
        "normalization": normalization,
        "nominal_range": nominal_range,
        "valid_when": "the corresponding Gymnasium presence mask is true",
        "source": source,
    }


_SIGNAL_SPECS = {key: _signal_spec(key) for key in _AVAILABLE_INFO_KEYS}


class _InfoProjector:
    """Project one native integer state row into selected public policy signals."""

    def __init__(
        self,
        keys: tuple[str, ...],
        *,
        num_envs: int,
        buffer_count: int,
        enabled: bool,
    ) -> None:
        self.keys = keys
        self.needs_native = enabled and bool(keys)
        derived = tuple(key for key in keys if key not in _NATIVE_SIGNAL_INDEX)
        self._buffers = [
            {
                key: np.empty(
                    (num_envs, *_SIGNAL_SPECS[key]["shape"]),
                    dtype=_SIGNAL_SPECS[key]["dtype"],
                )
                for key in derived
            }
            for _ in range(buffer_count)
        ]

    @staticmethod
    def _derived_array(key: str, count: int) -> np.ndarray:
        spec = _SIGNAL_SPECS[key]
        return np.empty((count, *spec["shape"]), dtype=spec["dtype"])

    @staticmethod
    def _fill_derived(key: str, out: np.ndarray, signals: np.ndarray) -> None:
        if key in _NORMALIZED_SOURCES:
            source, divisor = _NORMALIZED_SOURCES[key]
            np.divide(
                signals[:, _NATIVE_SIGNAL_INDEX[source]],
                np.float32(divisor),
                out=out,
                casting="unsafe",
            )
            return
        if key in _DYNAMIC_NORMALIZED_SOURCES:
            source, divisor = _DYNAMIC_NORMALIZED_SOURCES[key]
            np.divide(
                signals[:, _NATIVE_SIGNAL_INDEX[source]],
                signals[:, _NATIVE_SIGNAL_INDEX[divisor]],
                out=out,
                casting="unsafe",
            )
            return
        if key == "serve_phase":
            out[:] = ((signals[:, _NATIVE_SIGNAL_INDEX["tick"]] + 2) & 3).astype(
                np.int8
            )
            out[signals[:, _NATIVE_SIGNAL_INDEX["_awaiting_fire"]] == 0] = -1
            return
        if key == "brick_grid":
            words = np.stack(
                (
                    signals[:, _NATIVE_SIGNAL_INDEX["brick_mask"]].view(np.uint64),
                    signals[:, _NATIVE_SIGNAL_INDEX["brick_mask_high"]].view(np.uint64),
                ),
                axis=1,
            )
            bits = np.unpackbits(words.view(np.uint8), axis=1, bitorder="little")
            out[:] = bits[:, : 6 * 18].reshape((-1, 6, 18))
            return
        raise AssertionError(f"missing derived info implementation for {key!r}")

    def project(
        self,
        signals: np.ndarray,
        *,
        buffer_index: int | None,
        keys: tuple[str, ...] | None = None,
        copy_values: bool = False,
    ) -> dict[str, np.ndarray]:
        selected = self.keys if keys is None else keys
        result: dict[str, np.ndarray] = {}
        for key in selected:
            if key in _NATIVE_SIGNAL_INDEX:
                value = signals[:, _NATIVE_SIGNAL_INDEX[key]]
            else:
                value = (
                    self._derived_array(key, signals.shape[0])
                    if buffer_index is None
                    else self._buffers[buffer_index][key]
                )
                self._fill_derived(key, value, signals)
            result[key] = value.copy() if copy_values else value
        return result


def _enum_name(value: Any) -> str:
    name = getattr(value, "name", None)
    return str(name if name is not None else value).strip().lower()


def _is_stable_integration(value: Any) -> bool:
    name = getattr(value, "name", None)
    if name is not None and str(name).strip().lower() == "stable":
        return True
    if isinstance(value, str):
        return value.strip().lower() == "stable"
    if isinstance(value, (bool, np.bool_)):
        return False
    try:
        return operator.index(value) == 1
    except TypeError:
        return False


def _normalize_game(game: str | None) -> str:
    value = str(game)
    if value != _CANONICAL_GAME:
        raise ValueError(f"game must be {_CANONICAL_GAME!r}")
    return _CANONICAL_GAME


def _canonical_start_id(value: Any) -> str:
    return str(value)


def _resolve_actions(value: Any):
    name = _enum_name(value)
    if value is None or name in {"default", "none"}:
        custom = resolve_custom_action("simple", tables=ACTION_TABLES)
        return "custom_discrete", "simple", custom
    if name == "filtered" or (
        isinstance(value, (int, np.integer))
        and not isinstance(value, (bool, np.bool_))
        and int(value) == 1
    ):
        return "filtered", None, None
    if name in {"all", "discrete", "multi_discrete"} or (
        isinstance(value, int) and value in {0, 2, 3}
    ):
        raise ValueError(
            f"BreakoutVecEnv does not support built-in action mode {name!r}"
        )
    custom = resolve_custom_action(value, tables=ACTION_TABLES)
    unsupported = [
        labels
        for labels, masks in zip(custom.table, custom.masks, strict=True)
        if masks[0] not in _NATIVE_ACTION_BY_MASK
    ]
    if unsupported:
        raise ValueError(
            "BreakoutVecEnv cannot reproduce action combination(s): "
            + ", ".join(repr(value) for value in unsupported)
        )
    return "custom_discrete", custom.preset, custom


def _require_fixed_option(name: str, value: Any, expected: Any) -> None:
    if value != expected:
        raise ValueError(
            f"{name} must be {expected!r} for Atari Breakout compatibility"
        )


def _nonnegative_integer(name: str, value: Any, *, maximum: int | None = None) -> int:
    if isinstance(value, (bool, np.bool_)):
        raise TypeError(f"{name} must be a non-negative integer")
    try:
        result = operator.index(value)
    except TypeError as exc:
        raise TypeError(f"{name} must be a non-negative integer") from exc
    if result < 0:
        raise ValueError(f"{name} must be a non-negative integer")
    if maximum is not None and result > maximum:
        raise ValueError(f"{name} must be at most {maximum}")
    return result


def _reset_seeds(
    seed: int | Sequence[int | None] | None, num_envs: int
) -> tuple[int | None, ...]:
    if seed is None:
        return (None,) * num_envs
    if not isinstance(seed, (str, bytes, bytearray)) and np.isscalar(seed):
        base = _nonnegative_integer("seed", seed)
        return tuple(base + lane for lane in range(num_envs))
    if isinstance(seed, (str, bytes, bytearray)) or not isinstance(seed, Sequence):
        raise TypeError("seed must be an integer or a lane-aligned sequence")
    if len(seed) != num_envs:
        raise ValueError(f"seed must have length {num_envs}")
    values: list[int | None] = []
    for value in seed:
        values.append(
            None if value is None else _nonnegative_integer("seed entries", value)
        )
    return tuple(values)


def _validate_retro_compatibility_options(
    *,
    state: str | None,
    scenario: str | None,
    info: str | None,
    record: bool,
    players: int,
    inttype: Any,
    obs_type: Any,
    rom_path: str | None,
    noop_reset_max: int,
    use_fire_reset: bool,
    sticky_action_prob: float,
    reward_clip: bool,
) -> None:
    if scenario not in {None, "scenario"}:
        raise ValueError("scenario must be 'scenario' or None")
    if info not in {None, "data"}:
        raise ValueError("info must be 'data' or None; Atari signals are built in")
    _require_fixed_option("record", record, False)
    _require_fixed_option("players", players, 1)
    if not _is_stable_integration(inttype):
        raise ValueError("inttype must select the Stable integration")
    if _enum_name(obs_type) not in {"image", "0"}:
        raise ValueError("obs_type must be 'image'")
    _require_fixed_option("rom_path", rom_path, None)
    _nonnegative_integer(
        "noop_reset_max", noop_reset_max, maximum=np.iinfo(np.uint32).max
    )
    _require_fixed_option("use_fire_reset", use_fire_reset, False)
    _require_fixed_option("sticky_action_prob", float(sticky_action_prob), 0.0)
    _require_fixed_option("reward_clip", reward_clip, False)
    if state is not None and _canonical_start_id(state) not in _START_IDS:
        raise ValueError(f"unknown state {state!r}; expected one of {_START_IDS}")


class BreakoutVecEnv(VectorEnv):
    """Native deterministic Breakout vector environment.

    The only lifecycle is manual/disabled autoreset. Any selected lane may be
    reset at any time with ``reset(options={"reset_mask": mask})``. A terminal
    lane must be reset before the next call to ``step``.
    """

    metadata = {
        "autoreset_mode": AutoresetMode.DISABLED,
        "render_modes": ["rgb_array"],
        "render_fps": 60,
        "turbo_api_version": 2,
        "transition_transport": "numpy",
    }
    supports_live_snapshots = True

    def __init__(
        self,
        game: str,
        state: str | None = None,
        scenario: str | None = None,
        info: str | None = None,
        use_restricted_actions: Any | str | ActionTable = "default",
        record: bool = False,
        players: int = 1,
        inttype: Any = "stable",
        obs_type: Any = "image",
        render_mode: Literal["rgb_array"] | None = None,
        *,
        num_envs: int = 1,
        num_threads: int | None = None,
        rom_path: str | None = None,
        transport: str = "default",
        obs_copy: str = "safe_view",
        obs_resize: tuple[int, int] = (84, 84),
        obs_crop: tuple[int, int, int, int] | None = None,
        obs_crop_mode: str = "remove",
        obs_crop_fill: int = 0,
        obs_grayscale: bool = True,
        obs_resize_algorithm: str = "area",
        obs_layout: str = "chw",
        frame_skip: int = 4,
        frame_stack: int = 4,
        maxpool_last_two: bool = False,
        noop_reset_max: int = 0,
        use_fire_reset: bool = False,
        sticky_action_prob: float = 0.0,
        reward_clip: bool = False,
        info_filter: str | Mapping[str, Any] = "all",
        info_frame_stack_keys: Sequence[str] | None = None,
        state_catalog: Sequence[str] | None = None,
    ):
        if transport == "default":
            transport = "numpy"
        if transport != "numpy":
            raise ValueError("transport must be 'default' or 'numpy'")
        if info_frame_stack_keys is not None:
            raise ValueError("info_frame_stack_keys is unsupported and must be None")
        self.game = _normalize_game(game)
        action_mode, action_preset, custom_actions = _resolve_actions(
            use_restricted_actions
        )
        self.action_mode = action_mode
        self.action_preset = action_preset
        self.action_table = None if custom_actions is None else custom_actions.table
        self.action_meanings = (
            None if custom_actions is None else custom_actions.meanings
        )
        self.action_table_hash = (
            None if custom_actions is None else custom_actions.table_hash
        )
        self.buttons = tuple(BUTTONS)
        self.use_restricted_actions = use_restricted_actions
        self._custom_native_actions = (
            None
            if custom_actions is None
            else np.asarray(
                [_NATIVE_ACTION_BY_MASK[masks[0]] for masks in custom_actions.masks],
                dtype=np.uint8,
            )
        )
        _validate_retro_compatibility_options(
            state=state,
            scenario=scenario,
            info=info,
            record=record,
            players=players,
            inttype=inttype,
            obs_type=obs_type,
            rom_path=rom_path,
            noop_reset_max=noop_reset_max,
            use_fire_reset=use_fire_reset,
            sticky_action_prob=sticky_action_prob,
            reward_clip=reward_clip,
        )
        if state is not None and state_catalog is not None:
            raise ValueError("state and state_catalog are mutually exclusive")
        configured_catalog = (
            _START_IDS
            if state_catalog is None
            else tuple(_canonical_start_id(value) for value in state_catalog)
        )
        unknown_states = sorted(set(configured_catalog) - set(_START_IDS))
        if unknown_states:
            raise ValueError(f"state_catalog contains unknown states: {unknown_states}")
        if not configured_catalog:
            raise ValueError("state_catalog must not be empty")
        if len(set(configured_catalog)) != len(configured_catalog):
            raise ValueError("state_catalog must contain unique states")
        requested_state = (
            _canonical_start_id(state) if state is not None else configured_catalog[0]
        )
        if requested_state not in configured_catalog:
            raise ValueError("state must be present in state_catalog")
        self._default_start_index = configured_catalog.index(requested_state)
        self._catalog_to_engine = np.asarray(
            [_START_IDS.index(value) for value in configured_catalog],
            dtype=np.int32,
        )
        if maxpool_last_two:
            raise ValueError("maxpool_last_two is not implemented and must be False")
        if str(obs_layout).lower() != "chw":
            raise ValueError(
                "obs_layout is fixed to 'chw' for the rlab policy contract"
            )
        if not obs_grayscale:
            raise ValueError(
                "obs_grayscale is fixed to True for the rlab policy contract"
            )
        if obs_resize_algorithm != "area":
            raise ValueError(
                "obs_resize_algorithm is fixed to 'area' for the rlab policy contract"
            )
        if obs_crop_mode not in {"remove", "mask"}:
            raise ValueError("obs_crop_mode must be 'remove' or 'mask'")
        if (
            not isinstance(obs_crop_fill, int)
            or isinstance(obs_crop_fill, bool)
            or not 0 <= obs_crop_fill <= 255
        ):
            raise ValueError("obs_crop_fill must be an integer in [0, 255]")
        if render_mode not in (None, "rgb_array"):
            raise ValueError("render_mode must be None or 'rgb_array'")
        num_envs = int(num_envs)
        frame_skip = int(frame_skip)
        frame_stack = int(frame_stack)
        if num_envs <= 0 or frame_skip <= 0 or frame_stack <= 0:
            raise ValueError("num_envs, frame_skip, and frame_stack must be positive")
        if len(obs_resize) != 2 or min(int(v) for v in obs_resize) <= 0:
            raise ValueError("obs_resize must contain positive (height, width)")
        obs_h, obs_w = (int(obs_resize[0]), int(obs_resize[1]))
        crop = (
            (0, 0, 0, 0)
            if obs_crop is None
            else tuple(int(value) for value in obs_crop)
        )
        if len(crop) != 4 or min(crop) < 0:
            raise ValueError(
                "obs_crop must contain non-negative (top, bottom, left, right)"
            )
        if crop[0] + crop[1] >= RAW_HEIGHT or crop[2] + crop[3] >= RAW_WIDTH:
            raise ValueError("obs_crop removes the entire source image")
        if obs_copy not in {"copy", "safe_view", "unsafe_view"}:
            raise ValueError("obs_copy must be 'copy', 'safe_view', or 'unsafe_view'")

        if isinstance(info_filter, Mapping):
            self._info_mode = str(info_filter.get("mode", "all"))
            keys = info_filter.get("keys")
            if keys is None:
                self._info_keys = _STABLE_SIGNAL_NAMES
            else:
                if isinstance(keys, (str, bytes, bytearray)):
                    raise TypeError("info_filter keys must be a sequence of strings")
                try:
                    selected_keys = tuple(keys)
                except TypeError as exc:
                    raise TypeError(
                        "info_filter keys must be a sequence of strings"
                    ) from exc
                if not all(isinstance(key, str) for key in selected_keys):
                    raise TypeError("info_filter keys must be a sequence of strings")
                self._info_keys = selected_keys
        else:
            self._info_mode = str(info_filter)
            self._info_keys = _STABLE_SIGNAL_NAMES
        if self._info_mode not in {"all", "terminal", "none"}:
            raise ValueError("info_filter mode must be 'all', 'terminal', or 'none'")
        if len(set(self._info_keys)) != len(self._info_keys):
            raise ValueError("info_filter keys must be unique")
        unknown = set(self._info_keys) - set(_AVAILABLE_INFO_KEYS)
        if unknown:
            raise ValueError(f"unknown info keys: {sorted(unknown)}")
        self._stable_info_keys = _STABLE_SIGNAL_NAMES

        self.num_envs = num_envs
        self.frame_skip = frame_skip
        self.frame_stack = frame_stack
        self.noop_reset_max = _nonnegative_integer(
            "noop_reset_max", noop_reset_max, maximum=np.iinfo(np.uint32).max
        )
        self.obs_layout = "chw"
        self.obs_copy = obs_copy
        self.observation_ownership = (
            "owned"
            if obs_copy == "copy"
            else "unsafe_view"
            if obs_copy == "unsafe_view"
            else "safe_view"
        )
        self.observation_buffer_depth = (
            None if obs_copy == "copy" else 1 if obs_copy == "unsafe_view" else 2
        )
        self.signal_ownership = self.observation_ownership
        self.signal_buffer_depth = self.observation_buffer_depth
        self.autoreset_mode = AutoresetMode.DISABLED
        self.transport = transport
        self.render_mode = render_mode
        self.state_catalog = configured_catalog
        if action_mode == "filtered":
            self.single_action_space = gym.spaces.MultiBinary(_RETRO_BUTTON_COUNT)
            self.action_space = gym.spaces.Box(
                0,
                1,
                shape=(num_envs, _RETRO_BUTTON_COUNT),
                dtype=np.int8,
            )
        else:
            action_count = len(self.action_table)
            self.single_action_space = gym.spaces.Discrete(action_count)
            self.action_space = gym.spaces.MultiDiscrete(
                np.full(num_envs, action_count, dtype=np.int64)
            )
        self.single_observation_space = gym.spaces.Box(
            0, 255, shape=(frame_stack, obs_h, obs_w), dtype=np.uint8
        )
        self.observation_space = gym.spaces.Box(
            0, 255, shape=(num_envs, frame_stack, obs_h, obs_w), dtype=np.uint8
        )
        threads = num_envs if num_threads is None else int(num_threads)
        if threads <= 0:
            raise ValueError("num_threads must be positive")
        self.num_threads = threads
        self.native = NativeBreakoutVecEnv(
            num_envs,
            obs_h,
            obs_w,
            frame_skip,
            frame_stack,
            threads,
            list(crop),
            obs_crop_mode == "mask",
            obs_crop_fill,
        )
        count = 1 if obs_copy == "unsafe_view" else 2
        self._obs_buffers = [
            np.empty((num_envs, frame_stack, obs_h, obs_w), dtype=np.uint8)
            for _ in range(count)
        ]
        self._reward_buffers = [
            np.empty(num_envs, dtype=np.float32) for _ in range(count)
        ]
        self._terminated_buffers = [
            np.empty(num_envs, dtype=np.bool_) for _ in range(count)
        ]
        self._truncated_buffers = [
            np.empty(num_envs, dtype=np.bool_) for _ in range(count)
        ]
        self._signal_buffers = [
            np.empty((num_envs, len(_NATIVE_SIGNAL_NAMES)), dtype=np.int64)
            for _ in range(count)
        ]
        self._info_projector = _InfoProjector(
            self._info_keys,
            num_envs=num_envs,
            buffer_count=count,
            enabled=self._info_mode != "none",
        )
        self._buffer_index = 0
        self._active_state_indices = np.zeros(num_envs, dtype=np.int32)
        self._active_state_indices.setflags(write=False)
        self._initialized = np.zeros(num_envs, dtype=np.bool_)
        self._reset_rngs = [
            np.random.default_rng(lane) for lane in range(self.num_envs)
        ]
        self.closed = False
        self.live_snapshots_deterministic = True
        self.capabilities = MappingProxyType(
            {
                "supported_action_modes": ("filtered", "custom_discrete"),
                "supported_filtered_actions": _FILTERED_ACTION_ROWS,
                "supported_observation_layouts": ("chw",),
                "supported_observation_color_modes": ("grayscale",),
                "supported_resize_algorithms": ("area",),
                "supported_crop_modes": ("remove", "mask"),
                "supported_observation_copy_modes": (
                    "copy",
                    "safe_view",
                    "unsafe_view",
                ),
                "supported_transition_transports": ("numpy",),
                "supports_async_step": False,
                "supports_branching": True,
                "supports_device_api": False,
                "supports_emulator_ram": False,
                "supports_enemy_variants": False,
                "supports_fire_reset": False,
                "supports_info_frame_stack": False,
                "supports_live_snapshots": True,
                "supports_maxpool_last_two": False,
                "supports_noop_reset": True,
                "supports_per_lane_rgb": render_mode == "rgb_array",
                "supports_reward_clipping": False,
                "supports_snapshot_codec": False,
                "supports_state_catalog": True,
                "supports_sticky_action_prob": False,
                "supports_surface_variants": False,
            }
        )
        self.signal_schema = MappingProxyType(
            {
                key: MappingProxyType(
                    {
                        "dtype": _SIGNAL_SPECS[key]["dtype"],
                        "shape": _SIGNAL_SPECS[key]["shape"],
                        "available_on_reset": self._info_mode == "all",
                        "available_on_step": self._info_mode != "none",
                    }
                )
                for key in self._info_keys
            }
            if self._info_mode != "none"
            else {}
        )
        self.signal_metadata = MappingProxyType(
            {
                key: MappingProxyType(
                    {
                        metadata_key: value
                        for metadata_key, value in _SIGNAL_SPECS[key].items()
                        if metadata_key not in {"dtype", "shape"}
                    }
                )
                for key in self._info_keys
            }
            if self._info_mode != "none"
            else {}
        )

    def _next_buffers(self):
        index = self._buffer_index
        self._buffer_index = (self._buffer_index + 1) % len(self._obs_buffers)
        return (
            self._obs_buffers[index],
            self._reward_buffers[index],
            self._terminated_buffers[index],
            self._truncated_buffers[index],
            self._signal_buffers[index],
            index,
        )

    def _obs(self, observations: np.ndarray) -> np.ndarray:
        return observations.copy() if self.obs_copy == "copy" else observations

    def _infos(
        self,
        signals: np.ndarray,
        buffer_index: int,
        present: np.ndarray | None = None,
    ) -> dict[str, np.ndarray]:
        if self._info_mode == "none":
            return {}
        if present is None:
            present = np.ones(self.num_envs, dtype=np.bool_)
        if self._info_mode == "terminal":
            present = present & signals[
                :, _NATIVE_SIGNAL_INDEX["pending_reset"]
            ].astype(bool)
        result: dict[str, np.ndarray] = {}
        values = self._info_projector.project(
            signals,
            buffer_index=buffer_index,
            copy_values=self.obs_copy == "copy",
        )
        for key, value in values.items():
            result[key] = value
            result[f"_{key}"] = present.copy()
        return result

    def reset(self, *, seed: int | Sequence[int | None] | None = None, options=None):
        if self.closed:
            raise RuntimeError("cannot reset a closed environment")
        options = {} if options is None else dict(options)
        mask = options.pop("reset_mask", None)
        if mask is None:
            mask = np.ones(self.num_envs, dtype=np.bool_)
        if not isinstance(mask, np.ndarray):
            raise TypeError("options['reset_mask'] must be a NumPy array")
        if mask.shape != (self.num_envs,):
            raise ValueError(
                f"options['reset_mask'] must have shape ({self.num_envs},)"
            )
        if mask.dtype != np.bool_:
            raise TypeError("options['reset_mask'] must have dtype np.bool_")
        if not np.any(mask):
            raise ValueError("options['reset_mask'] must select at least one lane")
        snapshots = options.pop("snapshots", None)
        if snapshots is None:
            snapshot_values: list[Any | None] = [None] * self.num_envs
        else:
            if isinstance(snapshots, (str, bytes, bytearray)) or not isinstance(
                snapshots, Sequence
            ):
                raise TypeError("options['snapshots'] must be a lane-aligned sequence")
            if len(snapshots) != self.num_envs:
                raise ValueError(
                    f"options['snapshots'] must have length {self.num_envs}"
                )
            snapshot_values = list(snapshots)
        snapshot_mask = np.asarray(
            [value is not None for value in snapshot_values], dtype=np.bool_
        )
        if np.any(snapshot_mask & ~mask):
            raise ValueError("snapshots may only be supplied for selected reset lanes")
        reset_seeds = _reset_seeds(seed, self.num_envs)
        if any(reset_seeds[lane] is not None for lane in np.flatnonzero(snapshot_mask)):
            raise ValueError("snapshot reset lanes cannot also specify a seed")
        starts = options.pop("state_indices", None)
        if starts is None:
            starts = np.full(self.num_envs, self._default_start_index, dtype=np.int32)
            starts[snapshot_mask] = -1
        if not isinstance(starts, np.ndarray):
            raise TypeError("options['state_indices'] must be a NumPy array")
        if starts.shape != (self.num_envs,):
            raise ValueError(
                f"options['state_indices'] must have shape ({self.num_envs},)"
            )
        if starts.dtype != np.int32:
            raise TypeError("options['state_indices'] must have dtype np.int32")
        if np.any(starts[snapshot_mask] != -1):
            raise ValueError(
                "snapshot reset lanes must use -1 for the static start selector"
            )
        static_mask = mask & ~snapshot_mask
        selected_starts = starts[static_mask]
        if np.any((selected_starts < 0) | (selected_starts >= len(self.state_catalog))):
            raise ValueError(
                f"selected start indices must be in [0, {len(self.state_catalog) - 1}]"
            )
        if options:
            raise ValueError(f"unsupported reset options: {sorted(options)}")
        noop_counts = np.zeros(self.num_envs, dtype=np.uint32)
        next_reset_rngs = list(self._reset_rngs)
        for lane in np.flatnonzero(static_mask):
            lane_seed = reset_seeds[lane]
            generator = (
                np.random.default_rng(lane_seed)
                if lane_seed is not None
                else copy.deepcopy(self._reset_rngs[lane])
            )
            if self.noop_reset_max:
                noop_counts[lane] = generator.integers(
                    1, self.noop_reset_max + 1, dtype=np.uint64
                )
            next_reset_rngs[lane] = generator
        observations, rewards, terminated, truncated, signals, buffer_index = (
            self._next_buffers()
        )
        engine_starts = np.full(self.num_envs, -1, dtype=np.int32)
        engine_starts[static_mask] = self._catalog_to_engine[starts[static_mask]]
        if snapshots is None:
            self.native.reset_into(
                mask, engine_starts, noop_counts, observations, signals
            )
        else:
            self.native.reset_mixed_into(
                mask,
                engine_starts,
                noop_counts,
                snapshot_values,
                observations,
                signals,
            )
        self._reset_rngs = next_reset_rngs
        rewards[mask] = 0.0
        terminated[mask] = False
        truncated[mask] = False
        writable = self._active_state_indices.flags.writeable
        self._active_state_indices.setflags(write=True)
        self._active_state_indices[static_mask] = starts[static_mask]
        if np.any(snapshot_mask):
            engine_to_catalog = {
                int(engine_index): catalog_index
                for catalog_index, engine_index in enumerate(self._catalog_to_engine)
            }
            layout_ids = self.native.layout_ids()
            restored_indices = np.asarray(
                [engine_to_catalog.get(int(layout_id), -1) for layout_id in layout_ids],
                dtype=np.int32,
            )
            if np.any(restored_indices[snapshot_mask] < 0):
                raise ValueError("snapshot layout is absent from state_catalog")
            self._active_state_indices[snapshot_mask] = restored_indices[snapshot_mask]
        self._active_state_indices.setflags(write=writable)
        self._initialized[mask] = True
        infos = self._infos(signals, buffer_index, mask.copy())
        infos["state_index"] = self._active_state_indices.copy()
        infos["_state_index"] = mask.copy()
        start_source = snapshot_mask.astype(np.int8, copy=True)
        infos["start_source"] = start_source
        infos["_start_source"] = mask.copy()
        infos["noop_reset_count"] = noop_counts.astype(np.int64)
        infos["_noop_reset_count"] = static_mask.copy()
        return self._obs(observations), infos

    def step(self, actions):
        if self.closed:
            raise RuntimeError("cannot step a closed environment")
        if not isinstance(actions, np.ndarray):
            raise TypeError("actions must be a NumPy array")
        if not np.all(self._initialized):
            raise RuntimeError("all lanes must be reset before the first step")
        values = self._native_actions(actions)
        if values.shape != (self.num_envs,):
            raise ValueError(f"actions must have shape ({self.num_envs},)")
        observations, rewards, terminated, truncated, signals, buffer_index = (
            self._next_buffers()
        )
        self.native.step_into(
            values,
            observations,
            rewards,
            terminated,
            truncated,
            signals,
            self._info_projector.needs_native,
        )
        return (
            self._obs(observations),
            rewards,
            terminated,
            truncated,
            self._infos(signals, buffer_index),
        )

    def _native_actions(self, actions: Any) -> np.ndarray:
        if self.action_mode != "filtered":
            values = np.asarray(actions, dtype=np.int64).reshape(-1)
            if values.shape != (self.num_envs,):
                raise ValueError(f"actions must have shape ({self.num_envs},)")
            if values.size and (
                int(values.min()) < 0 or int(values.max()) >= len(self.action_table)
            ):
                raise ValueError(
                    f"actions must be in [0, {len(self.action_table) - 1}] "
                    f"for action_preset={self.action_preset!r}"
                )
            return self._custom_native_actions[values]
        if type(actions) is not np.ndarray:
            raise TypeError(
                "Stable-compatible filtered actions must be a plain NumPy array"
            )
        if actions.dtype != np.int8:
            raise TypeError(
                "Stable-compatible filtered actions must have dtype np.int8"
            )
        buttons = actions
        expected_shape = (self.num_envs, _RETRO_BUTTON_COUNT)
        if buttons.shape != expected_shape:
            raise ValueError(f"actions must have shape {expected_shape}")
        if np.any((buttons != 0) & (buttons != 1)):
            raise ValueError(
                "Stable-compatible eight-button transport must contain only 0 or 1"
            )
        matches = np.all(
            buttons[:, np.newaxis, :] == np.asarray(_FILTERED_ACTION_ROWS), axis=2
        )
        if not np.all(np.any(matches, axis=1)):
            raise ValueError(
                "Stable-compatible filtered-action rows must be exactly one of "
                "noop, FIRE, right, or left"
            )
        return np.argmax(matches, axis=1).astype(np.uint8)

    def active_state_indices(self) -> np.ndarray:
        return self._active_state_indices

    def get_state(self) -> list[bytes]:
        if self.closed:
            raise RuntimeError("cannot read state from a closed environment")
        return [bytes(value) for value in self.native.get_states()]

    def capture_snapshots(self, mask: np.ndarray) -> tuple[Any | None, ...]:
        if self.closed:
            raise RuntimeError("cannot capture snapshots from a closed environment")
        if not isinstance(mask, np.ndarray):
            raise TypeError("mask must be a NumPy array")
        if mask.shape != (self.num_envs,):
            raise ValueError(f"mask must have shape ({self.num_envs},)")
        if mask.dtype != np.bool_:
            raise TypeError("mask must have dtype np.bool_")
        if not np.any(mask):
            raise ValueError("mask must select at least one lane")
        if not np.all(self._initialized[mask]):
            raise RuntimeError("cannot capture a lane before its initial reset")
        return tuple(self.native.capture_snapshots(mask))

    def set_state(
        self, states: Sequence[bytes], reset_mask: np.ndarray | None = None
    ) -> None:
        if self.closed:
            raise RuntimeError("cannot restore state into a closed environment")
        if reset_mask is None:
            reset_mask = np.ones(self.num_envs, dtype=np.bool_)
        if (
            not isinstance(reset_mask, np.ndarray)
            or reset_mask.dtype != np.bool_
            or reset_mask.shape != (self.num_envs,)
        ):
            raise TypeError(
                f"reset_mask must be a bool NumPy array with shape ({self.num_envs},)"
            )
        state_values = list(states)
        layout_ids = np.asarray(
            self.native.validate_states(state_values, reset_mask), dtype=np.int32
        )
        engine_to_catalog = {
            int(engine_index): catalog_index
            for catalog_index, engine_index in enumerate(self._catalog_to_engine)
        }
        restored_indices = np.asarray(
            [engine_to_catalog.get(int(layout_id), -1) for layout_id in layout_ids],
            dtype=np.int32,
        )
        if np.any(restored_indices[reset_mask] < 0):
            raise ValueError("restored state layout is absent from state_catalog")

        observations, rewards, terminated, truncated, signals, _ = self._next_buffers()
        self.native.set_states_into(state_values, reset_mask, observations, signals)
        rewards[reset_mask] = 0.0
        terminated[reset_mask] = False
        truncated[reset_mask] = False
        self._initialized[reset_mask] = True
        self._active_state_indices.setflags(write=True)
        self._active_state_indices[reset_mask] = restored_indices[reset_mask]
        self._active_state_indices.setflags(write=False)

    def configure_lane(self, lane: int, **state: int) -> None:
        ordered = (
            "paddle_x",
            "ball_x",
            "ball_y",
            "ball_vx",
            "ball_vy",
            "bricks",
            "lives",
        )
        required = set(ordered)
        missing = required - state.keys()
        extra = state.keys() - required
        if missing or extra:
            raise ValueError(f"configure_lane requires {sorted(required)}")
        self.native.configure_lane(int(lane), *(int(state[name]) for name in ordered))

    def branch(
        self, states: Sequence[bytes], actions: Sequence[int] = (0, 1, 2, 3)
    ) -> dict[str, Any]:
        action_values = np.asarray(actions, dtype=np.uint8)
        next_states, flat_obs, rewards, terminated, flat_signals = self.native.branch(
            list(states), action_values.tolist()
        )
        count = len(states) * len(action_values)
        shape = self.single_observation_space.shape
        observations = (
            np.frombuffer(flat_obs, dtype=np.uint8).copy().reshape((count, *shape))
        )
        signals = np.asarray(flat_signals, dtype=np.int64).reshape(
            (count, len(_NATIVE_SIGNAL_NAMES))
        )
        branch_keys = (
            *_STABLE_SIGNAL_NAMES,
            *(key for key in self._info_keys if key not in _STABLE_SIGNAL_NAMES),
        )
        return {
            "next_states": [bytes(value) for value in next_states],
            "observations": observations,
            "rewards": np.asarray(rewards, dtype=np.float32),
            "terminated": np.asarray(terminated, dtype=np.bool_),
            "signals": self._info_projector.project(
                signals,
                buffer_index=None,
                keys=branch_keys,
                copy_values=True,
            ),
            "source_index": np.repeat(np.arange(len(states)), len(action_values)),
            "actions": np.tile(action_values, len(states)),
        }

    def render_lane(self, lane: int) -> np.ndarray | None:
        """Return a lane's 160x210 Stella RGB rendered frame without advancing."""
        if self.closed:
            raise RuntimeError("cannot render a closed environment")
        if isinstance(lane, (bool, np.bool_)):
            raise TypeError("lane must be an integer")
        try:
            lane_index = operator.index(lane)
        except TypeError:
            raise TypeError("lane must be an integer") from None
        if not 0 <= lane_index < self.num_envs:
            raise IndexError(
                f"lane must be in [0, {self.num_envs - 1}], got {lane_index}"
            )
        if self.render_mode != "rgb_array":
            return None
        indexed = np.frombuffer(
            self.native.render_indexed(lane_index), dtype=np.uint8
        ).reshape(RENDER_HEIGHT, RENDER_WIDTH)
        return _ATARI_2600_NTSC_PALETTE[indexed]

    def render(self):
        return self.render_lane(0)

    def get_images(self) -> list[np.ndarray | None]:
        if self.render_mode != "rgb_array":
            return [None for _ in range(self.num_envs)]
        return [self.render_lane(lane) for lane in range(self.num_envs)]

    def close(self):
        self.closed = True


__all__ = [
    "BreakoutVecEnv",
    "FIXED_POINT_ONE",
    "POLICY_INFO_KEYS",
    "RAW_HEIGHT",
    "RAW_WIDTH",
    "RENDER_HEIGHT",
    "RENDER_WIDTH",
]
