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

**env-BreakoutAtari2600-turbo-native** implements Atari 2600 Breakout in Rust
with a Python [Gymnasium] interface. Policies trained here should work in
[Stable Retro] when both environments use the same observation, action, and
episode settings within the
[documented compatibility contract](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md).
Native gameplay, parallel execution, and preprocessing are designed
to make environment stepping orders of magnitude faster than emulator-based
environments such as [Stable Retro].

<p align="center">
  <a href="https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/showcase-v0.5.15-20261005-style3/demo.mp4">
    <img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/showcase-v0.5.15-20261005-style3/demo.webp" alt="Same Actions: Stable Retro 1.0.1 and native 0.5.15 replaying the same policy actions; 362.30× environment throughput at n_envs=1" width="800" />
  </a>
</p>

<p align="center">
  <a href="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/showcase-v0.5.15-20261005-style3/benchmark.svg"><img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/showcase-v0.5.15-20261005-style3/benchmark.svg" alt="Side-by-side provider throughput bars at every measured environment count; open for full-size labels and confidence intervals" width="800" /></a>
</p>

[Open the full-size chart](https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/showcase-v0.5.15-20261005-style3/benchmark.svg). The table keeps the values readable at README width.

| n_envs | Stable Retro 1.0.1 SPS | Native 0.5.15 SPS | Paired speedup (95% CI) |
| ---: | ---: | ---: | :---: |
| 1 | 192.6 | 69,797.5 | 362.30× (358.47–366.10) |
| 2 | 377.4 | 124,814.6 | 331.04× (316.39–332.47) |
| 4 | 732.5 | 218,855.1 | 298.26× (290.64–305.13) |
| 8 | 1,032.3 | 258,955.4 | 251.21× (249.10–270.88) |
| 16 | 1,247.5 | 276,118.0 | 221.98× (219.31–224.02) |
| 32 | 1,342.4 | 353,326.8 | 263.21× (261.24–265.77) |
| 64 | 1,389.7 | 418,587.7 | 300.97× (298.86–302.43) |
| 128 | 1,408.1 | 361,149.5 | 256.48× (254.61–256.76) |
| 256 | 1,423.2 | 173,169.7 | 121.52× (120.64–122.43) |


Native **0.5.15** achieved **362.30×** the environment throughput of Stable
Retro **1.0.1** at `n_envs=1` (paired 95% CI **358.47–366.10×**) on an
AMD Ryzen 5 7600X. The chart retains every measured count through the adaptive
stop. Timing replays captured FirstWall policy actions with frame skip 2 and
stack 4; it includes stepping and preprocessing and excludes policy inference,
recording, and rendering. The animation uses a common 4× time compression and
the measured ratio; it is not a wall-clock recording. The matching excerpt
ends at score 429 with four lives and does not establish completed-wall parity
or a success rate. [Full-size chart](https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/showcase-v0.5.15-20261005-style3/benchmark.svg) · [Method, policy, and limitations](docs/speed-comparison.md) ·
[Download and verify the proof](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/showcase-v0.5.15-20261005-style3).

## Quick start

Requires Python 3.11+ on Apple-silicon macOS 11+ or x86-64 Linux with glibc 2.28+.
Playing needs no ROM, emulator, or Rust installation.

With [uv](https://docs.astral.sh/uv/) installed, create a project and open the
interactive player:

```bash
uv init --python 3.11 breakout-experiment
cd breakout-experiment
uv add "env-breakoutatari2600-turbo-native[play]"
uv run env-breakoutatari2600-turbo-native play
```

Move with ←/→ or A/D, press Space to serve, and Escape to quit. Press P to
pause or R to restart. Add `--uncapped` to play without a display-rate limit,
or `--help` to see all player options.

For an existing project, skip `uv init` and `cd`. If you only need the Python
API, install without the optional player: `uv add env-breakoutatari2600-turbo-native`.

## Train an agent

Train a PPO agent with the published [GradLab](https://github.com/tsilva/gradlab)
recipes. Training lives in GradLab, separately from this environment. Run either
version-pinned recipe from any directory:

```bash
# Standard PPO
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo

# PPO with learning-rate decay and KL-based update stopping
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo-stable-updates
```

These are full training runs. GradLab saves `final_model.zip` under `./runs`
and prints a version-pinned playback command when training finishes or stops safely. Run that
command to watch your trained policy play. Local runs disable W&B and checkpoint
evaluation by default.

## Use from Python

Save this as `quickstart.py` in your project, then run `uv run python quickstart.py`:

```python
import gymnasium as gym
import numpy as np

env = gym.make_vec(
    "env_breakoutatari2600_turbo_native:EnvBreakoutAtari2600TurboNative-v0",
    game="Breakout-Atari2600-v0",
    num_envs=16,
    num_threads=4,
)

try:
    obs, infos = env.reset(seed=42)
    actions = np.ones(env.num_envs, dtype=np.uint8)  # FIRE in every game
    obs, rewards, terminated, truncated, infos = env.step(actions)
    print(obs.shape)  # (16, 4, 84, 84)
finally:
    env.close()
```

This starts 16 independent games and serves the ball in each. Observations
contain four stacked 84×84 grayscale frames per game. Each step advances four
native game frames by default.

See the [full rollout example](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/examples/quickstart.py)
for a longer loop with selective resets and a local throughput measurement.

## Important behavior

- **Serve each ball:** actions are `0` noop, `1` FIRE, `2` right, and `3` left.
- **Reset completed games:** autoreset is disabled. Reset terminal lanes before
  stepping again; a Boolean `reset_mask` leaves other games unchanged. See the
  [reset example](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md#manual-reset).
- **Keep observations safely:** default observations reuse two rotating buffers.
  Use `obs_copy="copy"` when retaining observations across environment calls.
- **Understand rewards:** rewards are score changes, without life-loss or
  board-clear shaping. Episodes end after all five lives are lost; the
  environment does not generate truncation.

## Documentation and contributing

- [Environment reference](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/environment.md):
  actions, preprocessing, rendering, snapshots, branching, game signals,
  [Stable Retro Turbo] compatibility, and the optional Stable-Baselines3 adapter.
- [Performance comparison](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/speed-comparison.md)
  and [release validation](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/docs/release-validation.md):
  timing methodology, parity evidence, validation limits, and evidence ownership.
- [Contributing](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/CONTRIBUTING.md):
  source setup, development commands, and tests.
- [Support](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/SUPPORT.md)
  and [changelog](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases):
  installation help, supported platforms, and changes during the `0.x` community preview.

## Architecture

![breakout-native vector environment architecture](https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/architecture.png)

## License

[MIT](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/LICENSE).
See [third-party notices](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/THIRD_PARTY_NOTICES.md)
for Atari, [Stable Retro], ROM, and trademark boundaries.

[Gymnasium]: https://gymnasium.farama.org/
[Stable Retro]: https://stable-retro.farama.org/
[Stable Retro Turbo]: https://github.com/tsilva/env-StableRetro-turbo
