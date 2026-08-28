# Contributing

Thanks for helping make env-BreakoutAtari2600-turbo-native more useful and trustworthy for the
reinforcement-learning community.

## Before opening a change

- Search existing issues and discussions first.
- Use an issue for a bug report or proposed user-facing change.
- Do not submit ROMs, extracted game assets, reference frames, or save states.
- Keep the supported distribution boundary to Apple-silicon macOS and x86-64
  Linux.

## Development setup

Install [uv](https://docs.astral.sh/uv/) and a Rust toolchain, then run:

```bash
git clone https://github.com/tsilva/env-BreakoutAtari2600-turbo-native.git
cd env-BreakoutAtari2600-turbo-native
uv sync --locked --extra dev --extra play
make develop-release
```

## Required checks

```bash
uv run ruff check .
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked --lib
uv run pytest -m "not stable_retro"
```

Changes that can affect the `Start` state's physics, rewards, lifecycle,
observations, native rendering, or shared information must pass the sole live
Stable Retro Turbo oracle:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data \
make test-semantic-oracle \
  STABLE_RETRO_TURBO_REPO=/path/to/env-StableRetro-turbo
```

The operational provider release and checkout revision are selected only by
[`validation/stable-retro-turbo.json`](validation/stable-retro-turbo.json).
The required command fails when that exact checkout, its Turbo Vector API, or
the lawful Breakout ROM is unavailable or incompatible. It compares aligned
and seeded-noop resets plus representative trajectories through both public
vector APIs, including rendered frames, policy observations, rewards, score,
lives, termination, truncation, and every shared information value. The
provider is installed only into the local development environment and remains
outside the project lock, runtime dependencies, and distributions.

See
[`docs/release-validation.md`](docs/release-validation.md).

## Pull requests

Keep each pull request focused. Explain the user-visible result, tests run, and
any compatibility impact. Add or update tests for behavior changes and update
documentation when the public API changes. By contributing, you agree that your
contribution is distributed under this repository's MIT license.
