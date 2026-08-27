from importlib import resources

import numpy as np
import pytest
from env_breakoutatari2600_turbo_native import (
    ACTION_SETS,
    ACTION_TABLES,
    BreakoutVecEnv,
)

GAME_ID = "Breakout-Atari2600-v0"


def test_packaged_metadata_is_available_and_defines_simple():
    metadata = resources.files("env_breakoutatari2600_turbo_native").joinpath(
        "data", "Breakout-Atari2600-v0", "metadata.json"
    )

    assert metadata.is_file()
    assert ACTION_TABLES["simple"] == ((), ("BUTTON",), ("RIGHT",), ("LEFT",))
    assert ACTION_SETS["simple"] == ("noop", "button", "right", "left")


def test_simple_preset_exposes_exact_discrete_contract():
    env = BreakoutVecEnv(
        GAME_ID, use_restricted_actions="simple", num_envs=4, num_threads=1
    )
    try:
        assert env.action_preset == "simple"
        assert env.action_meanings == ("noop", "button", "right", "left")
        assert env.single_action_space.n == 4
        np.testing.assert_array_equal(env._native_actions([0, 1, 2, 3]), [0, 1, 2, 3])
    finally:
        env.close()


def test_inline_subset_and_reordering_map_to_native_commands():
    custom = BreakoutVecEnv(
        GAME_ID,
        use_restricted_actions=[["LEFT"], [], ["RIGHT"]],
        num_envs=3,
        num_threads=1,
    )
    native = BreakoutVecEnv(GAME_ID, num_envs=3, num_threads=1)
    try:
        assert custom.action_preset is None
        assert custom.action_meanings == ("left", "noop", "right")
        custom.reset()
        native.reset()
        actual = custom.step(np.asarray([0, 1, 2], dtype=np.int64))
        expected = native.step(np.asarray([3, 0, 2], dtype=np.int64))
        _assert_transition_equal(actual, expected)
    finally:
        custom.close()
        native.close()


@pytest.mark.parametrize(
    "value",
    ["all", "discrete", "multi_discrete"],
)
def test_unsupported_builtin_modes_are_rejected(value):
    with pytest.raises(ValueError, match="does not support"):
        BreakoutVecEnv(GAME_ID, use_restricted_actions=value)


def test_unreproducible_button_combination_is_rejected():
    with pytest.raises(ValueError, match="cannot reproduce"):
        BreakoutVecEnv(GAME_ID, use_restricted_actions=[["BUTTON", "RIGHT"]])


def test_default_is_the_named_simple_custom_discrete_table():
    default = BreakoutVecEnv(GAME_ID, num_envs=1)
    simple = BreakoutVecEnv(GAME_ID, use_restricted_actions="simple", num_envs=1)
    try:
        assert default.action_mode == "custom_discrete"
        assert default.action_preset == "simple"
        assert default.action_table == simple.action_table
        assert default.action_table_hash == simple.action_table_hash
    finally:
        default.close()
        simple.close()


def _assert_transition_equal(actual, expected):
    for actual_value, expected_value in zip(actual[:4], expected[:4], strict=True):
        np.testing.assert_array_equal(actual_value, expected_value)
    assert actual[4].keys() == expected[4].keys()
    for key in actual[4]:
        np.testing.assert_array_equal(actual[4][key], expected[4][key])


_NOOP_AND_FIRE = np.asarray(
    [[0, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 0]],
    dtype=np.int8,
)


@pytest.mark.parametrize(
    ("actions", "error", "message"),
    [
        (
            np.asarray(
                [[0, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 0, 1]],
                dtype=np.int8,
            ),
            ValueError,
            "exactly one of noop, FIRE, right, or left",
        ),
        (
            np.asarray(
                [[0, 0, 0, 0, 0, 0, 0, 0], [1, 0, 0, 0, 0, 0, 1, 0]],
                dtype=np.int8,
            ),
            ValueError,
            "exactly one of noop, FIRE, right, or left",
        ),
        (
            np.asarray(
                [[0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 1, 1]],
                dtype=np.int8,
            ),
            ValueError,
            "exactly one of noop, FIRE, right, or left",
        ),
        *[
            (
                np.eye(8, dtype=np.int8)[[0, button_index]],
                ValueError,
                "exactly one of noop, FIRE, right, or left",
            )
            for button_index in range(1, 6)
        ],
        (
            np.asarray(
                [[0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 1, 1, 0, 0, 0, 0]],
                dtype=np.int8,
            ),
            ValueError,
            "exactly one of noop, FIRE, right, or left",
        ),
        (
            np.asarray(
                [[0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 1, 0, 0, 1]],
                dtype=np.int8,
            ),
            ValueError,
            "exactly one of noop, FIRE, right, or left",
        ),
        (
            np.asarray(
                [[0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 2]],
                dtype=np.int8,
            ),
            ValueError,
            "only 0 or 1",
        ),
        (
            np.asarray(
                [[0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, -1, 0]],
                dtype=np.int8,
            ),
            ValueError,
            "only 0 or 1",
        ),
        *[
            (np.zeros((2, 8), dtype=dtype), TypeError, "dtype np.int8")
            for dtype in (np.bool_, np.uint8, np.int16, np.float32)
        ],
        (
            np.ma.array(
                [
                    [0, 0, 0, 0, 0, 0, 0, 0],
                    [0, 0, 0, 0, 0, 0, 0, 2],
                ],
                mask=[
                    [False, False, False, False, False, False, False, False],
                    [False, False, False, False, False, False, False, True],
                ],
                dtype=np.int8,
            ),
            TypeError,
            "plain NumPy array",
        ),
        (np.zeros(8, dtype=np.int8), ValueError, r"shape \(2, 8\)"),
        (np.zeros((1, 8), dtype=np.int8), ValueError, r"shape \(2, 8\)"),
        (np.zeros((2, 7), dtype=np.int8), ValueError, r"shape \(2, 8\)"),
        (np.zeros((2, 8, 1), dtype=np.int8), ValueError, r"shape \(2, 8\)"),
    ],
    ids=[
        "fire-right",
        "fire-left",
        "simultaneous-directions",
        "unnamed-button",
        "select",
        "reset",
        "up",
        "down",
        "multiple-unrelated",
        "direction-unrelated",
        "greater-than-one",
        "negative",
        "bool-dtype",
        "uint8-dtype",
        "int16-dtype",
        "float32-dtype",
        "masked-array",
        "missing-batch-axis",
        "wrong-lane-count",
        "wrong-button-count",
        "extra-axis",
    ],
)
def test_filtered_invalid_batches_are_rejected_atomically(actions, error, message):
    configuration = {
        "use_restricted_actions": "filtered",
        "num_envs": 2,
        "num_threads": 1,
        "frame_skip": 1,
        "noop_reset_max": 30,
        "render_mode": "rgb_array",
    }
    subject = BreakoutVecEnv(GAME_ID, **configuration)
    control = BreakoutVecEnv(GAME_ID, **configuration)
    try:
        subject.reset(seed=20260827)
        control.reset(seed=20260827)
        subject_transition = subject.step(_NOOP_AND_FIRE)
        control_transition = control.step(_NOOP_AND_FIRE)
        _assert_transition_equal(subject_transition, control_transition)
        returned_values = (
            *(value.copy() for value in subject_transition[:4]),
            {key: value.copy() for key, value in subject_transition[4].items()},
        )
        before_states = subject.get_state()
        before_indices = subject.active_state_indices().copy()
        before_frames = subject.get_images()

        with pytest.raises(error, match=message):
            subject.step(actions)

        assert subject.get_state() == before_states
        np.testing.assert_array_equal(subject.active_state_indices(), before_indices)
        for actual, expected in zip(subject.get_images(), before_frames, strict=True):
            np.testing.assert_array_equal(actual, expected)
        _assert_transition_equal(subject_transition, returned_values)

        valid_actions = np.asarray(
            [[0, 0, 0, 0, 0, 0, 0, 1], [0, 0, 0, 0, 0, 0, 1, 0]],
            dtype=np.int8,
        )
        expected_transition = control.step(valid_actions)
        actual_transition = subject.step(valid_actions)
        _assert_transition_equal(actual_transition, expected_transition)
        assert subject.get_state() == control.get_state()

        subject_reset = subject.reset()
        control_reset = control.reset()
        np.testing.assert_array_equal(subject_reset[0], control_reset[0])
        assert subject_reset[1].keys() == control_reset[1].keys()
        for key in subject_reset[1]:
            np.testing.assert_array_equal(subject_reset[1][key], control_reset[1][key])
        assert subject.get_state() == control.get_state()
    finally:
        subject.close()
        control.close()


def test_filtered_capability_discloses_exact_supported_rows():
    env = BreakoutVecEnv(
        GAME_ID, use_restricted_actions="filtered", num_envs=1, num_threads=1
    )
    try:
        assert env.capabilities["supported_filtered_actions"] == (
            (0, 0, 0, 0, 0, 0, 0, 0),
            (1, 0, 0, 0, 0, 0, 0, 0),
            (0, 0, 0, 0, 0, 0, 0, 1),
            (0, 0, 0, 0, 0, 0, 1, 0),
        )
    finally:
        env.close()
