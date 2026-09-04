<div align="center">
  <img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/logo.png" alt="env-BreakoutAtari2600-turbo-native logo" width="512" />

  **🕹️ Blazing-fast, deterministic Breakout for Reinforcement Learning 🕹️**
</div>

env-BreakoutAtari2600-turbo-native is a Python library for reinforcement-learning researchers
and engineers who need many reproducible Breakout games behind one Gymnasium
vector-environment API. Add it to a uv project from PyPI, create
`BreakoutVecEnv`, and step every lane with one NumPy action batch.

Fixed-point Rust physics owns game state and parallel stepping. Python exposes
manual reset, policy-ready observations, rendered frames, exact snapshots, and
side-effect-free action branching.

<div align="center">
  <img src="https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/demo.gif" alt="Native Breakout gameplay rendered by env-BreakoutAtari2600-turbo-native" width="320" />
</div>

## Install

Requires Python 3.11+ on Apple-silicon macOS 11+ or x86-64 Linux with glibc
2.28+.

Install [uv](https://docs.astral.sh/uv/), then add the library to your project:

```bash
uv add env-breakoutatari2600-turbo-native
```

Choose the corresponding requirement instead when you need an optional tool:

```bash
uv add "env-breakoutatari2600-turbo-native[play]"  # interactive Pygame player
```

To work from source, also install a Rust toolchain, then run:

```bash
git clone https://github.com/tsilva/env-BreakoutAtari2600-turbo-native.git
cd env-BreakoutAtari2600-turbo-native
uv sync --frozen --extra dev --extra play
make develop-release
```

## Use

```python
import gymnasium as gym
import numpy as np

env = gym.make_vec(
    "env_breakoutatari2600_turbo_native:EnvBreakoutAtari2600TurboNative-v0",
    game="Breakout-Atari2600-v0",
    num_envs=4096,
    num_threads=8,
)
obs, infos = env.reset()
obs, rewards, terminated, truncated, infos = env.step(
    np.zeros(env.num_envs, dtype=np.uint8)
)

done = terminated | truncated
if done.any():
    obs, reset_infos = env.reset(options={"reset_mask": done})
```

The module-qualified ID imports the package and registers the factory. This ID
is vector-only and requires an explicit `game`; `BreakoutVecEnv` remains
available for direct use.

## Train with GradLab

Training recipes and implementations live in
[GradLab](https://github.com/tsilva/rlab), keeping this repository focused on
the environment. Run a published recipe from any directory without installing
GradLab or cloning either repository.

For the default high-throughput PPO recipe:

```bash
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo
```

For PPO with learning-rate decay and KL-based update stopping:

```bash
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo-stable-updates
```

env-BreakoutAtari2600-turbo-native is ROM-free, so neither command needs a ROM path or registration.
GradLab shows live progress, writes a playable `final_model.zip` below `./runs`,
and prints the matching version-pinned `uvx ... play` command when training
finishes or is stopped safely. Local runs disable W&B and checkpoint evaluation
by default, so they cannot establish acceptance or promotion. These are
full-cap research recipes rather than short timed demos.

## Turbo Vector API v2

`BreakoutVecEnv` implements the strict Turbo Vector API v2:

- `metadata["turbo_api_version"]` is `2`,
  `metadata["transition_transport"]` is `"numpy"`, and `metadata["render_modes"]`
  advertises `rgb_array`.
- Immutable `capabilities` and `signal_schema` declarations describe supported
  features and the dtype, shape, and reset/step availability of every signal.
- `capabilities["supported_filtered_actions"]` discloses the exact noop, FIRE,
  right, and left eight-button rows accepted by the filtered action transport.
- `buttons`, `action_mode`, `action_preset`, `action_table`,
  `action_meanings`, and `action_table_hash` expose the resolved action
  semantics without provider-specific probing.
- `state_catalog` is an immutable ordered tuple. Callers select reset states
  with an `int32` `state_indices` array and inspect the read-only active indices
  with `active_state_indices()`; state sampling and lane routing remain
  caller-owned.
- `observation_ownership` and `observation_buffer_depth` declare the exact
  lifetime of returned observations; `signal_ownership` and
  `signal_buffer_depth` do the same for info values. The exported
  `POLICY_INFO_KEYS` tuple opts into paired raw and normalized ball, paddle,
  score, life, and brick-progress signals plus a 6×18 brick grid and serve
  phase without changing the default Stable-compatible infos;
  `signal_metadata` documents their units and normalization. Rendering is opt-in: with
  `render_mode="rgb_array"`, `render_lane(index)` renders one lane,
  `get_images()` renders all lanes, and `render()` renders lane zero. With the
  default `render_mode=None`, the first two methods return `None` and
  `get_images()` returns one `None` entry per lane.

Interesting live positions can be archived without advancing the game and
restored into any lane of the same environment:

```python
capture_mask = np.zeros(env.num_envs, dtype=np.bool_)
capture_mask[0] = True
captured = env.capture_snapshots(capture_mask)

restore_mask = np.zeros(env.num_envs, dtype=np.bool_)
restore_mask[3] = True
starts = [None] * env.num_envs
starts[3] = captured[0]
obs, infos = env.reset(
    options={"reset_mask": restore_mask, "snapshots": starts},
)
env.close()
```

Importing the package also preserves the Stable Retro Turbo-compatible
`Breakout-Atari2600-v0` vector ID. The complete lifecycle, configuration,
snapshot, and branching contract is in the
[environment documentation](docs/environment.md).

Stable-Baselines3 users can wrap the already-vectorized environment with the
optional, explicitly auto-resetting adapter described in the
[environment documentation](docs/environment.md#stable-baselines3). SB3
remains a separate install and is not part of the core dependency set.

## Commands

```bash
uv run --frozen --extra play env-breakoutatari2600-turbo-native play       # open the player
uv run --frozen --extra play env-breakoutatari2600-turbo-native play --uncapped
uv run --frozen ruff check .                               # lint Python
uv run --frozen pytest                                      # run Python tests
cargo test --locked --lib                                  # run Rust tests
RETRO_DATA_PATH=/lawful/stable_retro/data make parity       # diagnostic current-work parity
```

Append `--help` to the player command for its options. Matched performance
comparisons are provided by [TurboBench](https://github.com/tsilva/turbobench),
not by this repository.

## Notes

- Native actions are `0` noop, `1` FIRE, `2` right, and `3` left. The default
  policy observation is grayscale `uint8`, CHW, and shaped
  `(num_envs, 4, 84, 84)`.
- Filtered actions use `int8` batches shaped `(num_envs, 8)`. Only the exact
  binary noop, FIRE, right, and left rows disclosed by
  `capabilities["supported_filtered_actions"]` are accepted; unsupported
  buttons, combinations, dtypes, shapes, and values reject the whole batch
  before any lane advances.
- Rewards are score deltas using Atari row scoring. There is no life-loss or
  board-clear shaping. The cartridge presents two walls: the first refills
  after the next paddle return, the second ends at score 864 without another
  refill, and only losing all five lives terminates the episode.
- Autoreset is disabled. Reset terminated lanes explicitly with a Boolean
  `reset_mask`; unselected lanes remain byte-exact.
- With `noop_reset_max=N`, each static reset samples a seeded inclusive count
  from `1..N` and advances that many native console frames with noop, matching
  the conventional Atari reset distribution. FIRE is not
  issued automatically: `use_fire_reset` remains unavailable and the policy
  must start each serve.
- The canonical `Start` state targets original Stable Retro's 160×210 native indexed frame,
  lifecycle, physics, raster, rewards, collision behavior, and public trajectory
  values. In particular, `ball_y` uses the Atari RAM convention where zero
  means the serve is waiting for FIRE. Opt into rendered frames with
  `render_mode="rgb_array"`; `render()` then returns lane zero's canonical Stella
  RGB rendered frame while `render_lane(index)` selects any lane, separately from policy
  observations. Stable Retro's BGR-labeled RGB565 transport is
  normalized only at this human-facing boundary.
- Live validation requires a separately obtained lawful ROM. TurboBench owns
  cross-provider parity against pinned original `stable-retro==1.0.1`.
  `make parity` checks the current worktree diagnostically; `make parity-release`
  certifies the exact final wheel and produces a self-verifying receipt.
  Releases accept only the wheel and receipt produced by the protected parity
  workflow.
  No provider package, ROM, save state, or recorded reference frame is
  distributed by this project.
- Only Apple-silicon macOS and x86-64 Linux are supported. See
  [support](SUPPORT.md) and [release validation](docs/release-validation.md)
  for exact boundaries.
- The [specification compliance matrix](docs/specification-compliance.md) maps
  every project requirement to its maintained executable or non-code evidence.
- The project is a `0.x` community preview. Public changes are recorded in the
  [changelog](CHANGELOG.md). Serialized `get_state()` snapshots are portable
  only within the same package version and compatible configuration; live
  snapshot handles are session-local and intentionally not pickleable.

## Architecture

![env-BreakoutAtari2600-turbo-native architecture](https://raw.githubusercontent.com/tsilva/env-BreakoutAtari2600-turbo-native/main/architecture.png)

## License

[MIT](LICENSE). See [third-party notices](THIRD_PARTY_NOTICES.md) for Atari,
Stable Retro, ROM, and trademark boundaries.
