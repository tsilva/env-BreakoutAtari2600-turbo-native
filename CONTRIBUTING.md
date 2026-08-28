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
observations, rendering, or shared information must pass the sole live
Stable Retro Turbo oracle:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data \
make test-semantic-oracle \
  STABLE_RETRO_TURBO_REPO=/path/to/env-StableRetro-turbo \
  ORACLE_CANDIDATE=checkout \
  ORACLE_RECEIPT=/external/evidence/stable-retro-turbo-oracle.json
```

The operational provider release and checkout tree are selected only by
[`validation/stable-retro-turbo.json`](validation/stable-retro-turbo.json).
The required command fails when that exact pin, its Turbo Vector API, the
lawful Breakout ROM, a clean exact candidate, the fixed one-lane and multi-lane
workload, or any trajectory result is unavailable or incompatible. It compares
aligned and seeded-noop resets plus representative trajectories through both
public vector APIs, including rendered frames, policy observations, rewards,
score, lives, termination, truncation, and every shared information value. The
receipt binds the provider, candidate commit and version, configuration,
workload, and exact result. Provider and candidate installations are isolated
and remain outside the project lock, runtime dependencies, and distributions.

`make test-semantic-oracle-diagnostic PYTEST_ARGS=...` retains configurable
pytest diagnostics, but it is explicitly non-certifying and cannot generate a
release receipt. This separation prevents options such as `--collect-only`
from passing the release gate without executing the live workload.

Local receipts exercise the same fixed command, but release authority is
reserved for the repository's protected manual `Stable Retro Turbo oracle
evidence` workflow. The release candidate workflow accepts only that exact
successful run and its GitHub-attested receipt, never caller-supplied JSON.

See
[`docs/release-validation.md`](docs/release-validation.md).

## Pull requests

Keep each pull request focused. Explain the user-visible result, tests run, and
any compatibility impact. Add or update tests for behavior changes and update
documentation when the public API changes. By contributing, you agree that your
contribution is distributed under this repository's MIT license.
