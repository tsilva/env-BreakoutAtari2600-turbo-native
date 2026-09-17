<p align="center">
  <img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/logo.png" alt="env-BreakoutAtari2600-turbo-native logo" width="256" />
  <br />
  <strong>🕹️ Reproducible Breakout at training speed ⚡</strong>
</p>

<p align="center">
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/actions/workflows/ci.yml"><img src="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status" /></a>
  <a href="https://pypi.org/project/env-breakoutatari2600-turbo-native/"><img src="https://img.shields.io/pypi/v/env-breakoutatari2600-turbo-native.svg" alt="PyPI version" /></a>
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg" alt="Python 3.11 or newer" /></a>
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/env-breakoutatari2600-turbo-native.svg" alt="MIT license" /></a>
</p>

env-BreakoutAtari2600-turbo-native is a Python library for reinforcement-learning
researchers and engineers who need many reproducible Breakout games running in
parallel. It provides training observations and rewards through Gymnasium, with
one NumPy action batch per step. Install it from PyPI to use it in your own
training or evaluation loop.

env-BreakoutAtari2600-turbo-native is ROM-free. Normal use needs no emulator or
Stable Retro installation. A Rust core handles deterministic physics and
parallel stepping; Python exposes resets, rendering, snapshots, and action
branching.

<p align="center">
  <img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/demo.gif" alt="Native Breakout gameplay" width="320" />
</p>

## Install

Requires Python 3.11+ on Apple-silicon macOS 11+ or x86-64 Linux with glibc 2.28+.

With [uv](https://docs.astral.sh/uv/) installed, add the library to your project:

```bash
uv add env-breakoutatari2600-turbo-native
```

To play interactively, install the optional Pygame extra and open the player:

```bash
uv add "env-breakoutatari2600-turbo-native[play]"
uv run env-breakoutatari2600-turbo-native play
```

## Use

Save this as `example.py` in your project and run `uv run python example.py`:

```python
import gymnasium as gym
import numpy as np

env = gym.make_vec(
    "env_breakoutatari2600_turbo_native:EnvBreakoutAtari2600TurboNative-v0",
    game="Breakout-Atari2600-v0",
    num_envs=16,
    num_threads=4,
)
obs, infos = env.reset(seed=42)
obs, rewards, terminated, truncated, infos = env.step(
    np.full(env.num_envs, 1, dtype=np.uint8)  # FIRE starts each serve
)

done = terminated | truncated
if done.any():
    obs, reset_infos = env.reset(options={"reset_mask": done})
env.close()
```

Each lane is an independent game. Native actions are `0` noop, `1` FIRE,
`2` right, and `3` left. The default observations are grayscale `uint8` arrays
shaped `(num_envs, 4, 84, 84)`, with four native frames per step.

The module-qualified ID imports and registers the vector factory.
`BreakoutVecEnv` is also available for direct use. See the
[environment reference](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md)
for the Turbo Vector API v2 contract, Stable Retro Turbo compatibility,
filtered actions, policy signals, snapshots, and branching. Stable-Baselines3
users can install SB3 separately and use the explicit
[auto-reset adapter](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md#stable-baselines3).

### Brick layout info

Select both fields with `info_filter` to include them in reset and step info:

```python
from env_breakoutatari2600_turbo_native import BreakoutVecEnv

env = BreakoutVecEnv(
    "Breakout-Atari2600-v0",
    num_envs=1,
    info_filter={
        "mode": "all",
        "keys": ("brick_grid", "is_initial_brick_layout"),
    },
)
obs, infos = env.reset()
export = {
    "brick_grid": infos["brick_grid"][0].tolist(),
    "is_initial_brick_layout": bool(infos["is_initial_brick_layout"][0]),
}
env.close()
```

- `brick_grid` is a 6×18 integer matrix per lane, ordered top-to-bottom and
  left-to-right, with 1 for present bricks and 0 for absent bricks. It uses
  native visible state, without pixel detection. During startup it can be
  partial or blank even when `bricks_remaining` reports 108.
- `is_initial_brick_layout` is true through the initial animation, including
  blank setup frames. It becomes false on the first complete wall and stays
  false through later serves and wall refills. A new episode restarts tracking.

Both describe the returned observation's newest frame; step info describes
the successor state. The export above preserves a nested matrix and a boolean
for JSON serialization. Both fields are also included in `POLICY_INFO_KEYS`.

## Train with GradLab

Training implementations live in [GradLab](https://github.com/tsilva/gradlab).
Run either published PPO recipe from any directory:

```bash
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo-stable-updates
```

The second recipe adds learning-rate decay and KL-based update stopping.
These are full research runs. GradLab writes `final_model.zip` under `./runs`
and prints a version-pinned playback command when a run finishes or stops
safely. Local runs disable W&B and checkpoint evaluation by default.

## Develop

Install uv and Rust 1.85+, then run:

```bash
git clone https://github.com/tsilva/env-BreakoutAtari2600-turbo-native.git
cd env-BreakoutAtari2600-turbo-native
uv sync --frozen --extra dev --extra play
make develop-release
```

## Commands

Run these from the repository root after source setup:

```bash
uv run --frozen --extra play env-breakoutatari2600-turbo-native play  # open the player
uv run --frozen --extra play env-breakoutatari2600-turbo-native play --uncapped
make lint              # Python and Rust checks
make test              # Python and Rust tests
make develop-release   # rebuild the native extension after changes
```

Append `--help` to the player command for options, including the display-rate
limit. [TurboBench](https://github.com/tsilva/turbobench) provides performance
comparisons and cross-provider parity checks. See
[release validation](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/release-validation.md)
for `make parity` prerequisites and wheel certification.

## Notes

- Autoreset is disabled. Reset terminal lanes before stepping again; a Boolean
  `reset_mask` leaves unselected lanes unchanged. The policy must issue FIRE
  for each serve.
- Rewards are score changes without life-loss or board-clear shaping. Episodes
  end after all five lives are lost; the environment never generates truncation.
- Rendering is opt-in. Set `render_mode="rgb_array"`, then call
  `render_lane(index)` for a 160×210 Stella RGB frame. Rendering does not advance
  the game or alter policy observations.
- Default observations use two rotating buffers. Use `obs_copy="copy"` when
  retaining observations across environment calls.
- Serialized snapshots require the same package version and compatible
  configuration. Live snapshot handles belong to their originating environment.
- Canonical `Start` parity uses pinned original Stable Retro through TurboBench
  and requires a separately obtained lawful ROM. The package distributes no
  ROM, provider save state, recorded reference frame, or extracted game asset.
- This is a `0.x` community preview. Read the
  [changelog](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/CHANGELOG.md)
  for public changes and [support guide](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/SUPPORT.md)
  for platform limits and help. The
  [compliance matrix](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/specification-compliance.md)
  links requirements to their validation evidence.

## Architecture

![Breakout vector environment architecture](https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/architecture.png)

## License

[MIT](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/LICENSE).
See [third-party notices](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/THIRD_PARTY_NOTICES.md)
for Atari, Stable Retro, ROM, and trademark boundaries.
