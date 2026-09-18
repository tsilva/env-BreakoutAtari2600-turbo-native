"""Play native Breakout with Jev; Jev owns every action and prediction.

Setup: install this repository with its optional `play` dependencies for a window.
Use TYPESAFE_API_KEY from the environment, or pass --env-file .env.

Live, one native frame per decision, no decision/request caps:
    python examples/jev.py --env-file .env --decision-limit 0 --request-limit 0
Headless: add --no-display. Escape, Q, or window close exits visible play.
Offline smoke: --dry-run --no-display --decision-limit 8 --request-limit 8

JSONL logs include exact requests, decisions, latency, rewards, and outcomes.
One episode runs by default. API errors/timeouts stop without applying an action.
No forecasts, scripted fallback, TypeSafe SDK, or extra data files are needed.

Full controller memory is read from the public get_state() snapshot. This example
supports the BTO11 format in environment 0.5.13; it rejects unknown formats.
Embedded rules describe that format's canonical gameplay, not a second simulator.
"""

from __future__ import annotations

import argparse
import http.client
import json
import math
import multiprocessing as mp
import os
import shlex
import struct
import time
from copy import deepcopy
from pathlib import Path

import numpy as np
from env_breakoutatari2600_turbo_native import (
    FIXED_POINT_ONE,
    POLICY_INFO_KEYS,
    BreakoutVecEnv,
    __version__,
)

ACTIONS = {"noop": 0, "FIRE": 1, "right": 2, "left": 3}


CHOICE = {
    "type": "choice",
    "instructions": "Which one native action should the Breakout paddle take next to return "
    "the ball and keep it in play? You own every action, including FIRE for "
    "serves. The action lasts frames_per_decision native frames. The game is "
    "paused during inference. Coordinates are pixels, origin top left, "
    "positive y down; velocities are pixels per native frame. Ball x/y and "
    "paddle x are top-left positions. Paddle has inertia; noop releases input "
    "but may not stop instantly. ball_y_ram is a serve sentinel, not a screen "
    "coordinate. Brick rows are top-to-bottom, columns left-to-right, 1 means "
    "present. During initial_layout_animation the visible grid may be "
    "incomplete. controller_rules gives the exact paddle update equations and "
    "complete charge measurement table. Predict the paddle motion yourself "
    "for each candidate action, iterating once per native console frame. "
    "Predict where the descending ball will meet the paddle and choose an "
    "action that allows a catch. You may change actions after "
    "frames_per_decision frames. No predicted positions, catch labels, or "
    "recommended actions are supplied. You are playing Atari 2600 Breakout. "
    "Your objective is to make sure the paddle catches every returning ball "
    "and keeps the ball in play. Choose the next action to avoid a miss and "
    "preserve the ability to catch subsequent returns. When waiting for a "
    "serve, launch the ball with FIRE. Score is not the objective. "
    "simulator_rules contains the exact native transition source and all "
    "gameplay helper rules. native_state supplies every variable that affects "
    "future gameplay. Use those rules to calculate future states yourself, "
    "including delayed collisions, bounce angles, speed changes, serves and "
    "wall refill. Choose the action with the best chance of catching the ball "
    "and continuing to catch future returns. The left/right buttons control "
    "ONLY THE PADDLE CHARGE, not the ball. The ball velocity is autonomous "
    "until a collision. Select the paddle input that produces a paddle-ball "
    "collision, independently of the ball current direction. Noop is a real "
    "control action: the charge remains fixed while position smoothing "
    "continues.",
    "criteria": {
        "noop": {
            "native_action": 0,
            "button": "none",
            "charge_update": "unchanged",
            "held_next": False,
            "paddle_motion": "Smooth toward the previous measurement; existing "
            "drift continues.",
        },
        "FIRE": {
            "native_action": 1,
            "button": "FIRE",
            "charge_update": "unchanged",
            "held_next": False,
            "paddle_motion": "Same smoothing as noop. Launch only if "
            "awaiting_fire=true.",
        },
        "right": {
            "native_action": 2,
            "button": "right",
            "charge_update": "subtract repeat if charge > repeat",
            "held_next": True,
            "paddle_motion": "Same smoothing on this frame. Subsequent "
            "measurement changes raise target x.",
        },
        "left": {
            "native_action": 3,
            "button": "left",
            "charge_update": "add repeat if charge + repeat < 3856",
            "held_next": True,
            "paddle_motion": "Same smoothing on this frame. Subsequent "
            "measurement changes lower target x.",
        },
    },
}


CONTROLLER_RULES = {
    "units": "x and vx are pixels; charge, repeat, held and measure are raw controller "
    "integers.",
    "variables": "x=paddle.x, vx=paddle.vx, c=controller.charge, r=controller.repeat, "
    "h=controller.held, m=controller.measure, a=chosen native action.",
    "execution": "Apply these steps IN ORDER once per native console frame. Repeat "
    "frames_per_decision times with the same action. Use each updated state as "
    "the input for the next frame.",
    "steps": [
        "old_x = x; x = clamp(floor((floor(x) + 282 - m) / 2), 55, 191) - 47; vx = x - "
        "old_x. This uses the OLD measurement, before the current action changes "
        "charge.",
        "If h == 1: r = r + 1; then if r > 5: r = 60. If h == 0: leave r unchanged. "
        "This uses the PREVIOUS held flag.",
        "If a == 2 AND c > r: c = c - r. If a == 3 AND c + r < 3856: c = c + r. "
        "Otherwise leave c unchanged. These are strict guards, NOT saturating clamps.",
        "h = 1 if a is 2 or 3, otherwise h = 0.",
        "m = measurement from the LAST [lower_charge, measurement] row with "
        "lower_charge <= c. If c is below the first threshold, use the first "
        "measurement. If above the last, use the last measurement. Do NOT interpolate.",
    ],
    "charge_measurement_thresholds": [
        [1, 0],
        [272, 12],
        [295, 14],
        [318, 16],
        [341, 18],
        [365, 20],
        [388, 22],
        [411, 24],
        [447, 26],
        [470, 28],
        [493, 30],
        [516, 32],
        [539, 34],
        [563, 36],
        [586, 38],
        [609, 40],
        [633, 42],
        [657, 44],
        [680, 46],
        [703, 48],
        [733, 50],
        [757, 52],
        [780, 54],
        [803, 56],
        [828, 58],
        [851, 60],
        [874, 62],
        [897, 64],
        [920, 66],
        [943, 68],
        [966, 70],
        [991, 72],
        [1013, 74],
        [1036, 76],
        [1060, 78],
        [1083, 80],
        [1107, 82],
        [1130, 84],
        [1157, 86],
        [1180, 88],
        [1203, 90],
        [1228, 92],
        [1251, 94],
        [1273, 96],
        [1297, 98],
        [1320, 100],
        [1343, 102],
        [1366, 104],
        [1391, 106],
        [1413, 108],
        [1436, 110],
        [1460, 112],
        [1483, 114],
        [1507, 116],
        [1530, 118],
        [1553, 120],
        [1576, 122],
        [1599, 124],
        [1623, 126],
        [1647, 128],
        [1670, 130],
        [1693, 132],
        [1716, 134],
        [1739, 136],
        [1762, 138],
        [1786, 140],
        [1809, 142],
        [1832, 144],
        [1857, 146],
        [1880, 148],
        [1903, 150],
        [1925, 152],
        [1949, 154],
        [1972, 156],
        [1995, 158],
        [2020, 160],
        [2042, 162],
        [2066, 164],
        [2088, 166],
        [2112, 168],
        [2135, 170],
        [2158, 172],
        [2182, 174],
        [2205, 176],
        [2228, 178],
        [2253, 180],
        [2275, 182],
        [2299, 184],
        [2322, 186],
    ],
    "consequences": "Noop and FIRE keep charge unchanged but x can keep moving. Releasing or "
    "reversing does not reset repeat. The first frame of an action moves "
    "using the prior measurement. Current vx is an output of smoothing, not a "
    "velocity to extrapolate unchanged.",
    "ball_motion": "Between collisions, ball.x += ball.vx and ball.y += ball.vy each native "
    "console frame. Positive y points down. Ball width=2, height=4; paddle top "
    "y=189, height=4. Paddle occupies [x,x+width). Raster collisions are "
    "latched and resolved on a later native console frame; a vertical overlap "
    "estimate alone is not an exact catch test.",
}


SIMULATOR_RULES = r"""ATARI 2600 BREAKOUT — EXACT GAMEPLAY TRANSITION RULES
Objective: make sure the paddle catches every returning ball and keeps the ball in play. Avoid a miss and preserve the ability to catch subsequent returns. When waiting for a serve, launch the ball with FIRE. Score is not the objective. Rewards still equal score changes; the game's maximum score is 864 across two walls. You choose native actions noop=0, FIRE=1, right=2, left=3, including all serves.

The Rust source below defines the exact native transition and its helper functions. native_state contains the current gameplay variables using the same field names and units. FP=65536: coordinates and velocities in native_state use fixed-point integers; the separate ball/paddle objects use pixels. native_state.bricks is a hexadecimal bitmask string: parse it as an unsigned integer before applying the bit operations. wall_phase is the numeric enum value.

Rust integer division truncates toward zero. rem_euclid(FP) is the nonnegative remainder. Inclusive ranges '..=' include the endpoint. Boolean flags in native_state are true/false. Bitwise operators &, |, << have their usual integer meanings. The lookup uses the last threshold not greater than charge; it does not interpolate.

An environment step calls step_native with the SAME chosen action frames_per_decision times, stopping early on terminal. Apply all updates in the written order for each native console frame. Collision latches come from the previous frame. No clock time passes in the lane during API inference. Do not step a pending_reset terminal lane. Score 864 is a prototype stopping condition even though the native lane does not terminate there.

HUD score/life caches, image stacks and rendering caches do not affect any gameplay transition. Their display-only assignments in the source can be ignored for action selection. All variables that affect future gameplay are supplied. Rules and state are inputs only: calculate possible futures yourself. No action-specific predicted states, catch labels or recommended actions are supplied.

const FP: i32 = 1 << 16;
const BRICK_COLS: usize = 18;
const BRICK_ROWS: usize = 6;
const BRICK_ROW_POINTS: [i32; BRICK_ROWS] = [7, 7, 4, 4, 1, 1];
const FULL_BRICKS: u128 = (1u128 << (BRICK_COLS * BRICK_ROWS)) - 1;
const FULL_WALL_SCORE: i32 = 18 * (7 + 7 + 4 + 4 + 1 + 1);
const ATARI_TOP_SCORE: i32 = 2 * FULL_WALL_SCORE;
const BREAKTHROUGH_VY: i32 = 27 * FP / 8;

const COLLISION_WALL: i64 = 1;
const COLLISION_PADDLE: i64 = 2;
const COLLISION_BRICK: i64 = 4;
const COLLISION_LOSS: i64 = 8;

// Stable Retro's Stella paddle is an RC circuit driven by a digital key-repeat
// emulation.  Breakout samples that circuit once per two-line kernel.  These
// are the exact lower charge boundaries of the ROM-visible measurement for
// every charge reachable through Stella's digital left/right controls.
const PADDLE_MEASURE_THRESHOLDS: [(u16, u8); 89] = [
    (1, 0),
    (272, 12),
    (295, 14),
    (318, 16),
    (341, 18),
    (365, 20),
    (388, 22),
    (411, 24),
    (447, 26),
    (470, 28),
    (493, 30),
    (516, 32),
    (539, 34),
    (563, 36),
    (586, 38),
    (609, 40),
    (633, 42),
    (657, 44),
    (680, 46),
    (703, 48),
    (733, 50),
    (757, 52),
    (780, 54),
    (803, 56),
    (828, 58),
    (851, 60),
    (874, 62),
    (897, 64),
    (920, 66),
    (943, 68),
    (966, 70),
    (991, 72),
    (1013, 74),
    (1036, 76),
    (1060, 78),
    (1083, 80),
    (1107, 82),
    (1130, 84),
    (1157, 86),
    (1180, 88),
    (1203, 90),
    (1228, 92),
    (1251, 94),
    (1273, 96),
    (1297, 98),
    (1320, 100),
    (1343, 102),
    (1366, 104),
    (1391, 106),
    (1413, 108),
    (1436, 110),
    (1460, 112),
    (1483, 114),
    (1507, 116),
    (1530, 118),
    (1553, 120),
    (1576, 122),
    (1599, 124),
    (1623, 126),
    (1647, 128),
    (1670, 130),
    (1693, 132),
    (1716, 134),
    (1739, 136),
    (1762, 138),
    (1786, 140),
    (1809, 142),
    (1832, 144),
    (1857, 146),
    (1880, 148),
    (1903, 150),
    (1925, 152),
    (1949, 154),
    (1972, 156),
    (1995, 158),
    (2020, 160),
    // The startup charge ramp reaches values unavailable once Stella's
    // repeat acceleration locks to 60; 2042 is the observed central boundary.
    (2042, 162),
    (2066, 164),
    (2088, 166),
    (2112, 168),
    (2135, 170),
    (2158, 172),
    (2182, 174),
    (2205, 176),
    (2228, 178),
    (2253, 180),
    (2275, 182),
    (2299, 184),
    (2322, 186),
];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
enum WallPhase {
    First = 0,
    FirstCleared = 1,
    RefillArmed = 2,
    Second = 3,
    SecondCleared = 4,
}

impl WallPhase {
    fn walls_cleared(self) -> i64 {
        match self {
            Self::First => 0,
            Self::FirstCleared | Self::RefillArmed | Self::Second => 1,
            Self::SecondCleared => 2,
        }
    }

    fn bricks_destroyed(self, bricks_remaining: i64, initial_bricks: i64) -> i64 {
        match self {
            Self::First => initial_bricks - bricks_remaining,
            Self::FirstCleared | Self::RefillArmed => initial_bricks,
            Self::Second => 2 * initial_bricks - bricks_remaining,
            Self::SecondCleared => 2 * initial_bricks,
        }
    }

    fn from_byte(value: u8) -> Result<Self, &'static str> {
        match value {
            0 => Ok(Self::First),
            1 => Ok(Self::FirstCleared),
            2 => Ok(Self::RefillArmed),
            3 => Ok(Self::Second),
            4 => Ok(Self::SecondCleared),
            _ => Err("state has an invalid wall phase"),
        }
    }
}

const fn checker_mask() -> u128 {
    let mut mask = 0u128;
    let mut index = 0usize;
    while index < BRICK_COLS * BRICK_ROWS {
        let row = index / BRICK_COLS;
        let col = index % BRICK_COLS;
        if (row + col) % 2 == 0 {
            mask |= 1u128 << index;
        }
        index += 1;
    }
    mask
}

const fn tunnel_mask() -> u128 {
    let mut mask = FULL_BRICKS;
    let mut row = 1usize;
    while row < BRICK_ROWS {
        mask &= !(1u128 << (row * BRICK_COLS + 8));
        mask &= !(1u128 << (row * BRICK_COLS + 9));
        row += 1;
    }
    mask
}

const fn sparse_mask() -> u128 {
    let mut mask = 0u128;
    let mut col = 0usize;
    while col < BRICK_COLS {
        mask |= 1u128 << col;
        mask |= 1u128 << ((BRICK_ROWS - 1) * BRICK_COLS + col);
        col += 1;
    }
    mask
}

const LAYOUT_MASKS: [u128; 4] = [FULL_BRICKS, checker_mask(), tunnel_mask(), sparse_mask()];

const fn layout_wall_score(mask: u128) -> i64 {
    let mut total = 0;
    let mut index = 0;
    while index < BRICK_COLS * BRICK_ROWS {
        if mask & (1u128 << index) != 0 {
            total += BRICK_ROW_POINTS[index / BRICK_COLS] as i64;
        }
        index += 1;
    }
    total
}

const LAYOUT_INITIAL_BRICKS: [i64; 4] = [
    LAYOUT_MASKS[0].count_ones() as i64,
    LAYOUT_MASKS[1].count_ones() as i64,
    LAYOUT_MASKS[2].count_ones() as i64,
    LAYOUT_MASKS[3].count_ones() as i64,
];
const LAYOUT_MAX_SCORES: [i64; 4] = [
    2 * layout_wall_score(LAYOUT_MASKS[0]),
    2 * layout_wall_score(LAYOUT_MASKS[1]),
    2 * layout_wall_score(LAYOUT_MASKS[2]),
    2 * layout_wall_score(LAYOUT_MASKS[3]),
];

fn layout_mask(layout_id: i32) -> Option<u128> {
    match layout_id {
        0..=3 => Some(LAYOUT_MASKS[layout_id as usize]),
        _ => None,
    }
}

fn set_integer_preserving_fraction(value: i32, integer: i32) -> i32 {
    integer * FP + value.rem_euclid(FP)
}

fn step_native(lane: &mut Lane, action: u8) -> (f32, bool, bool) {
    let refilled = if lane.wall_phase == WallPhase::RefillArmed {
        lane.bricks = layout_mask(lane.layout_id).expect("validated layout");
        lane.wall_phase = WallPhase::Second;
        true
    } else {
        false
    };
    let score_before = lane.score;
    lane.last_collision = 0;
    lane.hud_score = lane.score;
    let collision_paddle_x = lane.paddle_x;
    update_paddle(lane, action);
    if lane.brick_contact {
        let y = lane.ball_y / FP;
        if y > 93 || y + 3 < 56 {
            lane.brick_contact = false;
        }
    }

    if lane.awaiting_fire {
        lane.hud_lives = lane.lives;
        if action == 1 {
            let serve = ((lane.tick + 2) & 3) as usize;
            let serve_x = [16, 78, 80, 142][serve];
            lane.awaiting_fire = false;
            lane.ball_x = set_integer_preserving_fraction(lane.ball_x, serve_x);
            lane.ball_y = set_integer_preserving_fraction(lane.ball_y, 122);
            lane.ball_vx = if serve & 1 == 0 { FP } else { -FP };
            lane.ball_vy = FP;
            lane.collision_latches = 0;
            lane.collision_count = 0;
            lane.steep_angle = true;
            lane.breakthrough = false;
            lane.narrow_paddle = false;
            lane.brick_contact = false;
        }
        lane.tick += 1;
        return (0.0, false, refilled);
    }

    if lane.ball_y / FP >= 217 {
        lane.lives -= 1;
        lane.awaiting_fire = true;
        lane.ball_y = set_integer_preserving_fraction(lane.ball_y, 9);
        lane.ball_vx = 0;
        lane.ball_vy = 0;
        lane.collision_latches = 0;
        lane.breakthrough = false;
        lane.narrow_paddle = false;
        lane.last_collision |= COLLISION_LOSS;
        lane.tick += 1;
        if lane.lives <= 0 {
            lane.pending_reset = true;
            return ((lane.score - score_before) as f32, true, refilled);
        }
        return ((lane.score - score_before) as f32, false, refilled);
    }

    // The ROM consumes collision latches produced by the preceding raster
    // frame.  This one-frame delay is essential at wall/brick corners.
    if lane.collision_latches & 1 != 0 {
        let y = lane.ball_y / FP;
        if y < 49 {
            lane.brick_contact = false;
            if lane.ball_vy < 0 {
                lane.ball_vy = -lane.ball_vy;
                lane.narrow_paddle = true;
                lane.last_collision |= COLLISION_WALL;
            }
        } else if !lane.brick_contact {
            let index = brick_at_ball(lane);
            if visible_bricks(lane) & (1u128 << index) != 0 {
                lane.bricks &= !(1u128 << index);
                let row = index / BRICK_COLS;
                lane.score += BRICK_ROW_POINTS[row];
                lane.ball_vy = -lane.ball_vy;
                if row <= 2 {
                    lane.breakthrough = true;
                    apply_breakthrough_speed(lane);
                }
                lane.brick_contact = true;
                lane.last_collision |= COLLISION_BRICK;
                if lane.bricks == 0 {
                    lane.wall_phase = match lane.wall_phase {
                        WallPhase::First => WallPhase::FirstCleared,
                        WallPhase::Second => WallPhase::SecondCleared,
                        phase => phase,
                    };
                }
            }
        }
    }
    if lane.collision_latches & 2 != 0 && lane.ball_vy > 0 {
        let center_offset = if lane.narrow_paddle { 5 } else { 6 };
        let relative_fp = collision_paddle_x + center_offset * FP - lane.ball_x;
        let crossing_branch = if lane.narrow_paddle {
            0 < relative_fp && relative_fp <= FP
        } else {
            (-FP < relative_fp) && (relative_fp <= 0)
        };
        if lane.narrow_paddle && relative_fp == 0 {
            lane.ball_vx = lane.ball_vx.abs();
            lane.steep_angle = true;
        } else if crossing_branch {
            lane.ball_x += if lane.ball_vx < 0 { 4 * FP } else { -4 * FP };
            lane.ball_vx = -lane.ball_vx.abs();
            lane.steep_angle = true;
        } else if relative_fp < 0 {
            lane.ball_vx = lane.ball_vx.abs();
        } else if relative_fp > 0 {
            lane.ball_vx = -lane.ball_vx.abs();
        } else {
            unreachable!("wide-paddle zero offset is a crossing branch");
        }
        if relative_fp != 0 && !crossing_branch {
            let steep_limit = if lane.narrow_paddle { 3 } else { 4 };
            lane.steep_angle = relative_fp.abs() <= steep_limit * FP;
        }
        lane.collision_count = (lane.collision_count + 1).min(12);
        apply_atari_speed(lane);
        lane.ball_vy = -lane.ball_vy.abs();
        lane.last_collision |= COLLISION_PADDLE;
        if lane.wall_phase == WallPhase::FirstCleared {
            lane.wall_phase = WallPhase::RefillArmed;
        }
    }
    // The ROM resolves the horizontal playfield latch after the paddle
    // branch. At the lower corners this lets the wall reflection win when
    // both objects latched on the same raster frame.
    if lane.collision_latches & 4 != 0 {
        let x = lane.ball_x / FP;
        if (x <= 8 && lane.ball_vx < 0) || (x >= 150 && lane.ball_vx > 0) {
            lane.ball_vx = -lane.ball_vx;
            lane.last_collision |= COLLISION_WALL;
        }
    }

    lane.ball_x += lane.ball_vx;
    lane.ball_y += lane.ball_vy;

    lane.collision_latches = raster_collision_latches(lane);
    lane.tick += 1;
    debug_assert!(lane.layout_id != 0 || lane.score <= ATARI_TOP_SCORE);
    ((lane.score - score_before) as f32, false, refilled)
}

fn paddle_measurement(charge: u16) -> u8 {
    let index = PADDLE_MEASURE_THRESHOLDS.partition_point(|&(lower, _)| lower <= charge);
    PADDLE_MEASURE_THRESHOLDS[index.saturating_sub(1)].1
}

fn charge_for_paddle_measurement(measurement: u8) -> u16 {
    PADDLE_MEASURE_THRESHOLDS
        .iter()
        .min_by_key(|&&(_, value)| value.abs_diff(measurement))
        .map(|&(charge, _)| charge)
        .unwrap_or(2048)
}

fn update_paddle(lane: &mut Lane, action: u8) {
    // The ROM first smooths the prior frame's measured controller value.
    let raw_x = lane.paddle_x / FP + 47;
    let target = 235 - lane.paddle_measure as i32;
    let next_raw = ((raw_x + target) / 2).clamp(55, 191);
    let previous_x = lane.paddle_x;
    lane.paddle_x = (next_raw - 47) * FP;
    lane.paddle_vx = lane.paddle_x - previous_x;

    if lane.paddle_held {
        lane.paddle_repeat += 1;
        if lane.paddle_repeat > 5 {
            // Stable Retro 1.0.1 embeds Stella 3.9.1, whose digital paddle
            // distance is 20 + (sensitivity << 3).  The canonical
            // sensitivity is five, so an accelerated hold advances the RC
            // charge by 60 per emulator frame.
            lane.paddle_repeat = 60;
        }
    }
    match action {
        2 if lane.paddle_charge > lane.paddle_repeat as u16 => {
            lane.paddle_charge -= lane.paddle_repeat as u16;
        }
        3 if lane.paddle_charge + (lane.paddle_repeat as u16) < 3856 => {
            lane.paddle_charge += lane.paddle_repeat as u16;
        }
        _ => {}
    }
    lane.paddle_held = matches!(action, 2 | 3);
    lane.paddle_measure = paddle_measurement(lane.paddle_charge);
}

fn brick_at_ball(lane: &Lane) -> usize {
    let y = lane.ball_y / FP;
    let row = ((y - 59).max(0) / 6).min(5) as usize;
    // The breakthrough kernel's red-row decoder is one raster pixel left of
    // the stored sprite coordinate. Lower rows and ordinary-speed contacts
    // decode the stored coordinate directly. This is visible at exact 8-pixel
    // column boundaries.
    let x = lane.ball_x / FP - i32::from(lane.breakthrough && row == 0);
    let col = ((x - 8).max(0) / 8).min(17) as usize;
    row * BRICK_COLS + col
}

fn visible_bricks(lane: &Lane) -> u128 {
    if lane.tick > 35 {
        return lane.bricks;
    }
    let mut mask = lane.bricks;
    for phase in 0..=lane.tick as usize {
        let byte = 35 - phase;
        let row = 5 - byte % 6;
        let (first, last) = match byte / 6 {
            5 => (0, 0),
            4 => (1, 4),
            3 => (5, 8),
            2 => (9, 10),
            1 => (11, 14),
            _ => (15, 17),
        };
        for column in first..=last {
            mask &= !(1u128 << (row * BRICK_COLS + column));
        }
    }
    mask
}

fn apply_atari_speed(lane: &mut Lane) {
    if lane.breakthrough {
        apply_breakthrough_speed(lane);
        return;
    }
    let group = (lane.collision_count / 4).min(3);
    let (x, y) = match (group, lane.steep_angle) {
        (0, false) => (3 * FP / 2, FP),
        (0, true) => (FP, 3 * FP / 2),
        (1, false) => (3 * FP / 2, 2 * FP),
        (1, true) => (FP / 2, 2 * FP),
        (2, _) => (2 * FP, FP),
        _ => (2 * FP, 2 * FP),
    };
    lane.ball_vx = if lane.ball_vx < 0 { -x } else { x };
    lane.ball_vy = if lane.ball_vy < 0 { -y } else { y };
}

fn apply_breakthrough_speed(lane: &mut Lane) {
    lane.ball_vx = if lane.ball_vx < 0 { -2 * FP } else { 2 * FP };
    lane.ball_vy = if lane.ball_vy < 0 {
        -BREAKTHROUGH_VY
    } else {
        BREAKTHROUGH_VY
    };
}

fn raster_collision_latches(lane: &Lane) -> u8 {
    let x = lane.ball_x / FP;
    let y = lane.ball_y / FP;
    let mut result = 0u8;
    if x <= 7 || x >= 151 {
        result |= 4;
    }
    if y <= 33 {
        result |= 1;
    } else if x < 152 && x + 1 >= 8 {
        for row in 0..BRICK_ROWS {
            let top = 57 + row as i32 * 6;
            let bottom = top + 5;
            // The breakthrough kernel draws the ball one scanline above its
            // stored Y coordinate and its collision latch follows those four
            // raster lines. The ordinary kernel has the ROM's wider edge
            // tolerance used by the slower ball modes.
            let vertical_overlap = if lane.breakthrough || row == 0 {
                y + 2 >= top && y - 1 <= bottom
            } else {
                y + 3 >= top - 1 && y <= bottom + 1
            };
            if vertical_overlap {
                // The TIA latches a playfield collision when either pixel of
                // the two-pixel ball overlaps a brick. The ROM subsequently
                // chooses the brick from the ball origin, so a ball straddling
                // two columns can latch against the neighbor and remove the
                // origin cell on the following frame.
                let first_col = ((x - 8).max(0) / 8).min(17) as usize;
                let last_col = ((x + 1 - 8).max(0) / 8).min(17) as usize;
                for col in first_col..=last_col {
                    if visible_bricks(lane) & (1u128 << (row * BRICK_COLS + col)) != 0 {
                        result |= 1;
                        break;
                    }
                }
                if result & 1 != 0 {
                    break;
                }
            }
        }
    }
    let paddle_x = lane.paddle_x / FP;
    let paddle_right = paddle_x + if lane.narrow_paddle { 11 } else { 15 };
    if y + 3 >= 189 && y <= 192 && x + 1 >= paddle_x && x <= paddle_right {
        result |= 2;
    }
    result
}
"""


def compact(value):
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def load_api_key(path):
    """Read only TYPESAFE_API_KEY, without executing shell or logging its value."""
    if os.environ.get("TYPESAFE_API_KEY") or path is None:
        return
    for line in path.read_text().splitlines():
        key, separator, value = line.strip().removeprefix("export ").partition("=")
        if separator and key.strip() == "TYPESAFE_API_KEY":
            try:
                parts = shlex.split(value, comments=True)
            except ValueError:
                raise ValueError("invalid TYPESAFE_API_KEY entry in env file") from None
            if len(parts) != 1 or not parts[0]:
                raise ValueError("empty or invalid TYPESAFE_API_KEY entry in env file")
            os.environ["TYPESAFE_API_KEY"] = parts[0]
            return


def game_state(info, recent, frames):
    """Read only public infos; never inspect native state or mutate physics."""

    def number(key):
        return int(info[key][0])

    def pixels(key):
        return number(key) / FIXED_POINT_ONE

    return {
        "frames_per_decision": frames,
        "ball": {
            "x": pixels("ball_x"),
            "y": pixels("ball_screen_y"),
            "vx": pixels("ball_vx"),
            "vy": pixels("ball_vy"),
            "width": 2,
            "height": 4,
            "ball_y_ram": number("ball_y"),
        },
        "paddle": {
            "x": pixels("paddle_x"),
            "y": 189,
            "vx": pixels("paddle_vx"),
            "width": number("paddle_width"),
        },
        "bricks": {
            "rows": ["".join(map(str, row)) for row in info["brick_grid"][0]],
            "origin": [8, 57],
            "cell_size": [8, 6],
            "remaining": number("bricks_remaining"),
            "walls_cleared": number("walls_cleared"),
            "initial_layout_animation": bool(info["is_initial_brick_layout"][0]),
        },
        "serve": {
            "waiting_for_fire": number("ball_y") == 0,
            "phase": number("serve_phase"),
        },
        "lives": number("lives"),
        "score": number("score"),
        "tick": number("tick"),
        "recent_actions": list(recent)[-8:],
    }


def snapshot_state(env):
    """Decode current gameplay fields, read-only; never advance or branch a lane."""
    blob = env.get_state()[0]
    layout = struct.Struct("<11i16sBQQQ8BH3B")
    if blob[:5] != b"BTO11" or len(blob) < 5 + layout.size:
        raise ValueError("unsupported or truncated native snapshot; expected BTO11")
    names = (
        "paddle_x paddle_vx ball_x ball_y ball_vx ball_vy score hud_score lives "
        "hud_lives layout_id bricks wall_phase tick last_collision stack_head "
        "pending_reset awaiting_fire collision_latches collision_count steep_angle "
        "breakthrough narrow_paddle brick_contact paddle_charge paddle_repeat "
        "paddle_held paddle_measure"
    ).split()
    state = dict(zip(names, layout.unpack_from(blob, 5), strict=True))
    for key in ("hud_score", "hud_lives", "stack_head"):
        del state[key]
    state["bricks"] = f"0x{int.from_bytes(state['bricks'], 'little'):032x}"
    for key in (
        "pending_reset",
        "awaiting_fire",
        "steep_angle",
        "breakthrough",
        "narrow_paddle",
        "brick_contact",
        "paddle_held",
    ):
        state[key] = bool(state[key])
    return state


def decision_state(env, info, history, frames):
    state = game_state(info, history[-8:], frames)
    native = snapshot_state(env)
    state["variant"] = "simulator"
    state["controller"] = {
        name: int(native["paddle_" + name])
        for name in ("charge", "repeat", "held", "measure")
    }
    state["controller"]["current_target_x"] = 188 - state["controller"]["measure"]
    state["dynamics"] = {
        key: int(native["last_collision" if key == "collision_events" else key])
        for key in (
            "collision_latches",
            "collision_count",
            "steep_angle",
            "breakthrough",
            "narrow_paddle",
            "brick_contact",
            "wall_phase",
            "collision_events",
            "pending_reset",
            "layout_id",
        )
    }
    mask = int(native["bricks"], 16)
    state["bricks"]["logical_mask_words_hex"] = [
        f"{mask & ((1 << 64) - 1):016x}",
        f"{mask >> 64:016x}",
    ]
    state["reset_noop_frames"] = state["tick"] - len(history) * frames
    state["action_history"] = []
    for action in history:
        if state["action_history"] and state["action_history"][-1]["action"] == action:
            state["action_history"][-1]["native_frames"] += frames
        else:
            state["action_history"].append({"action": action, "native_frames": frames})
    state["controller_rules"] = CONTROLLER_RULES
    state["simulator_rules"] = SIMULATOR_RULES
    state["native_state"] = native
    return state


def request_body(state, model):
    payload = {"state": state, "model": model, "questions": {"action": CHOICE}}
    payload = deepcopy(payload)
    state = payload["state"]
    ball, paddle = state["ball"], state["paddle"]
    state["current_geometry_pixels"] = {
        "ball_left": ball["x"],
        "ball_right_exclusive": ball["x"] + ball["width"],
        "ball_top": ball["y"],
        "ball_bottom_exclusive": ball["y"] + ball["height"],
        "paddle_left": paddle["x"],
        "paddle_right_exclusive": paddle["x"] + paddle["width"],
        "paddle_center": paddle["x"] + paddle["width"] / 2,
        "ball_center": ball["x"] + ball["width"] / 2,
        "ball_center_minus_paddle_center": (
            ball["x"] + ball["width"] / 2 - paddle["x"] - paddle["width"] / 2
        ),
    }
    overlap = (
        int(ball["x"]) + 1 >= int(paddle["x"])
        and int(ball["x"]) <= int(paddle["x"]) + paddle["width"] - 1
    )
    state["current_observations"] = {
        "horizontal_ball_paddle_relation_now": (
            "overlapping"
            if overlap
            else "ball entirely to the left of paddle"
            if ball["x"] < paddle["x"]
            else "ball entirely to the right of paddle"
        ),
        "ball_horizontal_direction_now": (
            "left" if ball["vx"] < 0 else "right" if ball["vx"] > 0 else "stationary"
        ),
        "ball_vertical_direction_now": (
            "down toward paddle"
            if ball["vy"] > 0
            else "up away from paddle"
            if ball["vy"] < 0
            else "stationary"
        ),
        "paddle_direction_last_native_frame": (
            "left"
            if paddle["vx"] < 0
            else "right"
            if paddle["vx"] > 0
            else "stationary"
        ),
        "meaning": "Observations of the current state only, not forecasts or recommended actions.",
    }
    return payload


def validate_answer(response):
    """Fail closed; never normalize, substitute, or infer a missing action."""
    reason = "shape"
    try:
        answer = response["answers"]["action"]
        choice = answer["choice"]
        probabilities = answer["probabilities"]
        confidence = answer["confidence"]
        reason = "action_or_type"
        if answer["type"] != "choice" or choice not in ACTIONS:
            raise ValueError
        reason = "probability_keys"
        if set(probabilities) != set(ACTIONS):
            raise ValueError
        reason = "numeric_range"
        values = [confidence, *probabilities.values()]
        if any(
            type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1
            for v in values
        ):
            raise ValueError
        reason = f"probability_sum={sum(probabilities.values()):.6f}"
        # Live Jev rounds to hundredths; four rounded probabilities can lose/gain
        # up to 0.02 in total. Preserve the values rather than renormalizing them.
        rounded = all(
            abs(v * 100 - round(v * 100)) < 1e-6 for v in probabilities.values()
        )
        tolerance = 0.0200001 if rounded else 0.001
        if not math.isclose(sum(probabilities.values()), 1.0, abs_tol=tolerance):
            raise ValueError
        return {
            "choice": choice,
            "action": ACTIONS[choice],
            "probabilities": probabilities,
            "confidence": confidence,
            # The live service occasionally disagrees with its documented argmax
            # convention. The explicit choice owns control; log the discrepancy.
            "choice_matches_probability_max": (
                probabilities[choice] + 1e-6 >= max(probabilities.values())
            ),
        }
    except (KeyError, TypeError, ValueError, AttributeError):
        # Do not echo arbitrary server content, headers, or credentials.
        raise ValueError(f"invalid_choice_response:{reason}") from None


def http_choice(payload, timeout):
    """One HTTPS request, no redirects or automatic retries."""
    connection = http.client.HTTPSConnection("api.typesafe.ai", timeout=timeout)
    try:
        connection.request(
            "POST",
            "/v1/systemone",
            compact(payload),
            headers={
                "Authorization": "Bearer " + os.environ["TYPESAFE_API_KEY"],
                "Content-Type": "application/json",
            },
        )
        response = connection.getresponse()
        if response.status != 200:
            return {"error": f"http_{response.status}"}
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            return {"error": "response_too_large"}
        return {"decision": validate_answer(json.loads(raw))}
    except TimeoutError:
        return {"error": "timeout"}
    except (ValueError, UnicodeError) as exc:
        detail = (
            str(exc)
            if str(exc).startswith("invalid_choice_response:")
            else "invalid_json"
        )
        return {"error": "invalid_choice_response", "detail": detail}
    except (OSError, http.client.HTTPException):
        return {"error": "network_error"}
    finally:
        connection.close()


def api_worker(pipe, controller, timeout, mock_delay):
    """Persistent killable worker. It never owns or advances the environment."""
    mock_index = 0
    try:
        while True:
            payload = pipe.recv()
            started = time.perf_counter()
            if controller == "mock":
                time.sleep(mock_delay)
                # Fixed cycle exercises all actions; this is NOT Jev or ball tracking.
                choices = ["FIRE", "noop", "right", "left"]
                choice = choices[mock_index % 4]
                mock_index += 1
                answer = {
                    "type": "choice",
                    "choice": choice,
                    "confidence": 1.0,
                    "probabilities": {a: float(a == choice) for a in ACTIONS},
                }
                result = {"decision": validate_answer({"answers": {"action": answer}})}
            else:
                result = http_choice(payload, timeout)
            result["service_latency_ms"] = (time.perf_counter() - started) * 1000
            pipe.send(result)
    except (EOFError, BrokenPipeError):
        pass
    finally:
        pipe.close()


class Worker:
    def __init__(self, args):
        context = mp.get_context("spawn")
        self.pipe, child = context.Pipe()
        self.process = context.Process(
            target=api_worker,
            args=(child, args.controller, args.timeout, args.mock_delay),
            daemon=True,
        )
        self.process.start()
        child.close()

    def close(self):
        self.pipe.close()
        if self.process.is_alive():
            self.process.terminate()
        self.process.join(timeout=1)
        if self.process.is_alive():
            self.process.kill()
            self.process.join()


class Display:
    def __init__(self, enabled):
        self.pg = None
        if enabled:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame

            self.pg = pygame
            pygame.display.init()
            self.screen = pygame.display.set_mode((480, 630))
            self.clock = pygame.time.Clock()

    def pump(self, env, status):
        if self.pg is None:
            return True
        pg = self.pg
        for event in pg.event.get():
            if event.type == pg.QUIT or (
                event.type == pg.KEYDOWN and event.key in (pg.K_ESCAPE, pg.K_q)
            ):
                return False
        surface = pg.surfarray.make_surface(env.render().transpose(1, 0, 2))
        self.screen.blit(pg.transform.scale(surface, self.screen.get_size()), (0, 0))
        pg.display.set_caption("Breakout | " + status)
        pg.display.flip()
        self.clock.tick(60)
        return True

    def close(self):
        if self.pg is not None:
            self.pg.display.quit()


def stop_reason(state, terminated, truncated, decisions, decision_limit):
    if state["score"] >= 864:
        return "maximum_score"
    if terminated:
        return "terminated"
    if truncated:
        return "truncated"
    if decision_limit > 0 and decisions >= decision_limit:
        return "decision_limit"
    return None


def run_episode(args, controller, seed, episode, log, budget, display):
    env = BreakoutVecEnv(
        "Breakout-Atari2600-v0",
        state="Start",
        num_envs=1,
        num_threads=1,
        use_restricted_actions="simple",
        frame_skip=args.frames_per_decision,
        noop_reset_max=args.noop_reset_max,
        info_filter={"mode": "all", "keys": (*POLICY_INFO_KEYS, "tick")},
        render_mode="rgb_array" if args.display else None,
    )
    worker = None
    started = time.perf_counter()
    decisions = requests = mock_requests = 0
    reward_sum = 0.0
    latencies, service_latencies = [], []
    recent = []
    reason = None
    terminated = truncated = False
    pending = None
    failure = None

    def emit(kind, **fields):
        log.write(
            compact(
                {
                    "event": kind,
                    "controller": controller,
                    "seed": seed,
                    "episode": episode,
                    **fields,
                }
            )
            + "\n"
        )
        log.flush()

    try:
        _, info = env.reset(seed=seed)
        state = game_state(info, recent, args.frames_per_decision)
        initial_tick = state["tick"]
        emit("reset", state=state, noop_reset_count=int(info["noop_reset_count"][0]))
        worker = Worker(args)
        while reason is None:
            status = (
                f"{controller} seed={seed} score={state['score']} "
                f"lives={state['lives']} decisions={decisions}"
            )
            if not display.pump(env, status):
                reason = "user_exit"
                break
            if args.request_limit > 0 and budget[0] >= args.request_limit:
                reason = "request_limit"
                break
            payload = request_body(
                decision_state(
                    env,
                    info,
                    recent,
                    args.frames_per_decision,
                ),
                args.model,
            )
            decision_started = time.perf_counter()
            budget[0] += 1
            requests += int(controller == "jev")
            mock_requests += int(controller == "mock")
            pending = budget[0]
            emit("request", request_count=budget[0], payload=payload)
            try:
                worker.pipe.send(payload)
            except (BrokenPipeError, OSError):
                reason = "worker_exit"
                break
            while not worker.pipe.poll():
                if not display.pump(env, status + " waiting for decision"):
                    reason = "user_exit"
                    break
                if time.perf_counter() - decision_started >= args.timeout:
                    reason = "timeout"
                    break
                if not worker.process.is_alive():
                    reason = "worker_exit"
                    break
                if not args.display:
                    time.sleep(0.002)
            if reason:
                break
            if time.perf_counter() - decision_started >= args.timeout:
                reason = "timeout"
                break
            try:
                result = worker.pipe.recv()
            except (EOFError, OSError):
                reason = "worker_exit"
                break
            if "error" in result:
                reason = result["error"]
                failure = result
                break
            latency = (time.perf_counter() - decision_started) * 1000
            # Final event check: a queued quit must not apply the returned decision.
            if not display.pump(env, status):
                reason = "user_exit"
                break
            decision = result["decision"]
            latencies.append(latency)
            if result["service_latency_ms"] is not None:
                service_latencies.append(result["service_latency_ms"])
            _, reward, terms, truncs, info = env.step(
                np.array([decision["action"]], dtype=np.int64)
            )
            decisions += 1
            reward_sum += float(reward[0])
            terminated, truncated = bool(terms[0]), bool(truncs[0])
            recent.append(decision["action"])
            after = game_state(info, recent, args.frames_per_decision)
            reason = stop_reason(
                after, terminated, truncated, decisions, args.decision_limit
            )
            emit(
                "decision",
                input=state,
                **decision,
                latency_ms=latency,
                service_latency_ms=result["service_latency_ms"],
                request_count=budget[0],
                reward=float(reward[0]),
                outcome=reason,
                terminated=terminated,
                truncated=truncated,
                after=after,
            )
            state = after
            pending = None
    except KeyboardInterrupt:
        reason = "user_exit"
    finally:
        if worker is not None:
            worker.close()
        env.close()
    elapsed = time.perf_counter() - started
    native_frames = state["tick"] - initial_tick
    if pending is not None:
        emit(
            "request_failed",
            request_count=pending,
            outcome=reason,
            latency_ms=(time.perf_counter() - decision_started) * 1000,
            action_applied=False,
            failure=failure,
        )
    summary = {
        "controller": controller,
        "seed": seed,
        "episode": episode,
        "outcome": reason,
        "score": state["score"],
        "lives": state["lives"],
        "reward": reward_sum,
        "decisions": decisions,
        "requests": requests,
        "mock_requests": mock_requests,
        "native_frames": native_frames,
        "simulated_seconds": native_frames / 60,
        "wall_seconds": elapsed,
        "native_fps_wall": native_frames / elapsed,
        "realtime_factor": native_frames / 60 / elapsed,
        "decision_latency_mean_ms": float(np.mean(latencies)) if latencies else None,
        "decision_latency_p95_ms": float(np.percentile(latencies, 95))
        if latencies
        else None,
        "service_latency_mean_ms": float(np.mean(service_latencies))
        if service_latencies
        else None,
        "terminated": terminated,
        "truncated": truncated,
        "survival_censored": not terminated,
    }
    emit(
        "episode_end",
        **{
            k: v
            for k, v in summary.items()
            if k not in ("controller", "seed", "episode")
        },
    )
    return summary


def parser():
    result = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    result.add_argument("--env-file", type=Path)
    result.add_argument("--model", default="jev-latest")
    result.add_argument("--seed", type=int, default=0)
    result.add_argument("--frames-per-decision", type=int, default=1)
    result.add_argument(
        "--request-limit",
        type=int,
        default=32,
        help="total requests; 0 means unlimited",
    )
    result.add_argument(
        "--decision-limit",
        type=int,
        default=500,
        help="decisions per episode; 0 means unlimited",
    )
    result.add_argument(
        "--episode-limit",
        type=int,
        default=1,
        help="consecutive seeds, starting at --seed",
    )
    result.add_argument("--timeout", type=float, default=30)
    result.add_argument("--noop-reset-max", type=int, default=30)
    result.add_argument(
        "--display", action=argparse.BooleanOptionalAction, default=True
    )
    result.add_argument(
        "--dry-run",
        action="store_true",
        help="offline fixed action cycle, never presented as Jev",
    )
    result.add_argument(
        "--output", type=Path, default=Path("runs") / time.strftime("jev-%Y%m%d-%H%M%S")
    )
    return result


def main(argv=None):
    cli = parser()
    args = cli.parse_args(argv)
    if (
        min(args.frames_per_decision, args.episode_limit) <= 0
        or not math.isfinite(args.timeout)
        or args.timeout <= 0
    ):
        cli.error("cadence, episode limit, and timeout must be positive")
    if min(args.request_limit, args.decision_limit, args.noop_reset_max, args.seed) < 0:
        cli.error("limits, reset noops, and seed must be non-negative")
    if not args.dry_run:
        try:
            load_api_key(args.env_file)
        except (OSError, ValueError):
            cli.error("could not read TYPESAFE_API_KEY from --env-file")
        if not os.environ.get("TYPESAFE_API_KEY"):
            cli.error("TYPESAFE_API_KEY is unavailable; --dry-run runs an offline mock")
    args.controller = "mock" if args.dry_run else "jev"
    args.mock_delay = 0
    args.output.mkdir(parents=True, exist_ok=False)
    summaries, budget = [], [0]
    display = Display(args.display)
    try:
        with (args.output / "events.jsonl").open("w") as log:
            log.write(
                compact(
                    {
                        "event": "configuration",
                        "environment_version": __version__,
                        "args": {
                            **vars(args),
                            "output": str(args.output),
                            "env_file": str(args.env_file) if args.env_file else None,
                        },
                    }
                )
                + "\n"
            )
            for episode in range(1, args.episode_limit + 1):
                summary = run_episode(
                    args,
                    args.controller,
                    args.seed + episode - 1,
                    episode,
                    log,
                    budget,
                    display,
                )
                summaries.append(summary)
                print(compact(summary), flush=True)
                if summary["outcome"] not in (
                    "terminated",
                    "truncated",
                    "maximum_score",
                    "decision_limit",
                ):
                    break
                if args.request_limit > 0 and budget[0] >= args.request_limit:
                    break
    finally:
        display.close()
        (args.output / "summary.json").write_text(
            json.dumps(summaries, indent=2) + "\n"
        )
    return int(
        any(
            s["outcome"]
            not in (
                "terminated",
                "truncated",
                "maximum_score",
                "decision_limit",
                "request_limit",
                "user_exit",
            )
            for s in summaries
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
