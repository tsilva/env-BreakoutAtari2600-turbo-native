<p align="center">
  <img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/logo.png" alt="breakout-native logo" width="256" />
  <br />
  <!-- repo-tagline:start -->
  <strong>🕹️ Reproducible Breakout for parallel RL experiments ⚡</strong>
  <!-- repo-tagline:end -->
</p>

<p align="center">
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/actions/workflows/ci.yml"><img src="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/actions/workflows/ci.yml/badge.svg?branch=main" alt="CI status" /></a>
  <a href="https://pypi.org/project/env-breakoutatari2600-turbo-native/"><img src="https://img.shields.io/pypi/v/env-breakoutatari2600-turbo-native.svg" alt="PyPI version" /></a>
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/pyproject.toml"><img src="https://img.shields.io/badge/python-%E2%89%A53.11-blue.svg" alt="Python 3.11 or newer" /></a>
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/LICENSE"><img src="https://img.shields.io/pypi/l/env-breakoutatari2600-turbo-native.svg" alt="MIT license" /></a>
</p>

breakout-native is a Python library for reinforcement-learning researchers and
engineers running Atari 2600 Breakout experiments. Run independent games in
parallel, replay exact states, and compare action branches without a ROM or
emulator. Install the package to try a Python rollout or play interactively.

The project env-BreakoutAtari2600-turbo-native is ROM-free; normal use also needs
no Stable Retro installation. Its Rust core provides deterministic gameplay
through a Gymnasium vector interface and supports the documented Stable Retro
Turbo Breakout replacement contract.

<p align="center">
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/demo.mp4">
    <picture>
      <source srcset="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/demo.webp" type="image/webp" />
      <img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/demo.gif" alt="Stable Retro and breakout-native replaying the same trained-policy actions at a diagnostic 35.13× relative environment speed" width="800" />
    </picture>
  </a>
</p>

**Diagnostic preview:** native `0.5.13` and original Stable Retro `1.0.1` replay
the same GradLab FirstWall PPO actions. The excerpt matches exactly; the full
episode had a later parity mismatch. Playback illustrates a busy-host,
one-lane environment throughput ratio, excluding policy inference and rendering.
Its frame skip 2, four-frame stack, and 84×84 grayscale preprocessing follow
the checkpoint's saved training contract. See the
[comparison method and evidence inventory](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/speed-comparison.md)
for pixel settings, replay checks, and timing limits, or inspect the
[media manifest](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/demo-manifest.json).
Full-policy playback and replay archives remain local.

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

## Try a rollout

Save this as `quickstart.py` in your project and run `uv run python quickstart.py`.
The same code is available in [the runnable example](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/examples/quickstart.py):

```python
from time import perf_counter

import gymnasium as gym
import numpy as np

env = gym.make_vec(
    "env_breakoutatari2600_turbo_native:EnvBreakoutAtari2600TurboNative-v0",
    game="Breakout-Atari2600-v0",
    num_envs=16,
    num_threads=4,
)

try:
    obs, _ = env.reset(seed=42)
    total_reward = 0.0
    started = perf_counter()
    for step in range(1024):
        # This fixed action cycle is a smoke workload, not a trained policy.
        action = 1 if step % 4 == 0 else 2
        actions = np.full(env.num_envs, action, dtype=np.uint8)
        obs, rewards, terminated, truncated, _ = env.step(actions)
        total_reward += float(rewards.sum())
        done = terminated | truncated
        if done.any():
            obs, _ = env.reset(options={"reset_mask": done})
    elapsed = perf_counter() - started
    print(f"observation shape: {obs.shape}")
    print(f"total reward: {total_reward:g}")
    print(f"transitions: {1024 * env.num_envs}")
    print(f"transitions/second: {1024 * env.num_envs / elapsed:,.0f} (local diagnostic)")
finally:
    env.close()
```

Each lane is an independent game. Native actions are `0` noop, `1` FIRE,
`2` right, and `3` left. The default observations are grayscale `uint8` arrays
shaped `(num_envs, 4, 84, 84)`, with four native frames per step.
The printed rate is a local smoke measurement from a fixed action cycle; it is
not a matched performance comparison or an agent learning result.

The module-qualified ID registers the vector factory; `BreakoutVecEnv` is also
available for direct use. The
[environment reference](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md)
covers Stable Retro Turbo compatibility, filtered actions, policy signals,
snapshots, and branching. See its
[info-filtering examples](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md#info-filtering)
for the visible brick grid and initial-layout flag, or the
[Stable-Baselines3 adapter](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md#stable-baselines3)
for explicit auto-reset behavior; install SB3 separately.

## Train with GradLab

Training implementations live in [GradLab](https://github.com/tsilva/gradlab).
The following recipe names were checked against the pinned GradLab `0.1.1`
release. Run either from any directory:

```bash
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo-stable-updates
```

The second recipe adds learning-rate decay and KL-based update stopping.
These are full research runs. GradLab writes `final_model.zip` under `./runs`
and prints a version-pinned playback command when a run finishes or stops
safely. Local runs disable W&B and checkpoint evaluation by default.

## Develop

Install uv and Rust (the repository pins its toolchain), then run:

```bash
git clone https://github.com/tsilva/env-BreakoutAtari2600-turbo-native.git
cd env-BreakoutAtari2600-turbo-native
uv sync --locked --extra dev --extra play
make develop-release
```

## Commands

Run these from the repository root after source setup:

```bash
uv run --frozen python examples/quickstart.py                      # run a rollout
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

- Use the [Arcade Learning Environment](https://github.com/Farama-Foundation/Arcade-Learning-Environment)
  for the established multi-game Atari benchmark. Compare results only when game
  settings, observations, actions, rewards, and reset rules match.
- The [v0.5.15 parity receipt](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/download/v0.5.15/turbobench-parity-receipt.tar.gz)
  records canonical `Start` checks against pinned original Stable Retro for its
  exact final wheel. It measures neither throughput nor equivalence with ALE.
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

![breakout-native vector environment architecture](https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/architecture.png)

## License

[MIT](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/LICENSE).
See [third-party notices](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/THIRD_PARTY_NOTICES.md)
for Atari, Stable Retro, ROM, and trademark boundaries.
