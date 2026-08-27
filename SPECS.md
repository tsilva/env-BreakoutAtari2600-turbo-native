## PROJECT PURPOSE

`env-BreakoutAtari2600-turbo-native` is a ROM-free, high-throughput Python vector-environment library for reinforcement-learning researchers and engineers that runs independent Atari 2600 Breakout lanes without an emulator or Stable Retro runtime while preserving deterministic canonical gameplay and a supported Stable Retro Turbo replacement contract.

## PROJECT REQUIREMENTS

### Product boundary

- Use `env-BreakoutAtari2600-turbo-native` as the project and GitHub repository name, `env-breakoutatari2600-turbo-native` as the Python distribution name, and `env_breakoutatari2600_turbo_native` as the public Python import package; current project-owned identities must not use any former project, distribution, import, or command identifier.
- Normal environment use must require no Atari ROM, emulator, original Stable Retro, or Stable Retro Turbo installation.
- The project must distribute no Atari ROM, cartridge dump, provider save state, recorded reference frame, or extracted game asset; oracle validation may use a separately and lawfully obtained ROM.
- Training implementations must remain outside this repository.
- Stable-Baselines3 and interactive-player dependencies must remain optional rather than core dependencies.
- Supported binary platforms must be limited to Apple-silicon macOS and x86-64 Linux.

### Vector environment

- The vector environment must step every lane from one batched action input and return observations and transition results that conform to its declared Gymnasium spaces.
- Within the same package version, a lane’s trajectory must be bit-identical across supported binary platforms, batch sizes, neighboring-lane behavior, execution orders, and thread counts when its configuration, aligned state, and actions match.
- The core vector environment must never automatically reset a terminal lane, must reject attempts to step it before reset, and must allow callers to reset selected lanes while leaving unselected lanes byte-exact.
- Explicit adapters may automatically reset completed lanes only while preserving terminal observations and leaving other lanes unchanged.
- Serialized snapshots must support exact continuation within the same package version and compatible environment configuration; their format need not be compatible across versions.
- Live snapshot handles must remain valid only within their originating environment and its lifecycle.
- Callers must be able to evaluate action branches from snapshots without mutating the source environment or snapshot.
- Native actions must be `0` noop, `1` FIRE, `2` right, and `3` left.
- Action tables must accept the game-owned `simple` table and exact caller-supplied subsets or reorderings of reproducible native actions.
- Stable-compatible filtered actions must retain the eight-button transport, accept only exact noop, FIRE, right, and left rows, disclose those valid rows, and reject every unsupported button or combination without normalization.
- The default policy observation per lane must be a grayscale `uint8` CHW stack of four 84×84 frames produced using four native frames per environment step.
- Policy observations and rendered frames must derive independently from the same native 160×210 indexed frame.
- Rendering must be opt-in, must never advance or mutate game state, must support selecting an individual lane, and must produce the canonical 160×210 Stella RGB rendered frame.
- The interactive player must support a configurable display-rate limit and visible uncapped play.

### Canonical compatibility

- Within the documented reproducible subset, callers must be able to replace Stable Retro Turbo with `env-BreakoutAtari2600-turbo-native` for `Breakout-Atari2600-v0` without changing game, state, observation, action, reward, reset, termination, truncation, or shared-information semantics; unsupported provider options must fail immediately.
- The pinned Stable Retro Turbo release must be the sole semantic oracle and compatibility target for canonical `Start` behavior.
- After aligning the starting state or reset outcome, every externally observable canonical `Start` trajectory detail must match the oracle under equivalent configuration and actions, including rendered frames, policy observations, rewards, score, lives, termination, truncation, and shared information values.
- Equivalent seeds need not select identical stochastic reset traces, but seeded reset distributions and semantics must match the oracle.
- Changes capable of affecting canonical `Start` physics, rewards, lifecycle, observations, rendering, or shared information must be acceptance-tested side by side against the pinned Stable Retro Turbo oracle.
- The canonical `Breakout-Atari2600-v0` `Start` state must reproduce the oracle’s 160×210 geometry, 18×6 brick wall, 2×4 ball, initially 16×4 ceiling-narrowing paddle, five-life counter, FIRE-gated serves, paddle inertia, delayed collision latches, breakthrough speed, score raster, scanline priority, and wall and corner behavior.
- With `noop_reset_max=N`, each selected static reset must reproducibly sample an inclusive `1..N` raw-frame noop count independently of frame skip, must never issue FIRE, and must leave unselected lanes unchanged.
- Rewards must equal the score change over each environment step using Atari row scoring, without life-loss or board-clear shaping.
- Clearing the first brick wall must refill the same layout one native frame after the next paddle return.
- Clearing the second brick wall must leave the board permanently empty at the Atari maximum score of 864.
- Canonical play must terminate only after all five lives are lost, and the environment itself must never generate truncation.
- Shared information values must match the oracle’s Atari conventions, including reporting inactive `ball_y` as zero.
- Canonical gameplay semantics and the supported replacement contract must remain protected even when auxiliary public APIs evolve during `0.x`.
