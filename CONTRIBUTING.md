# Contributing

Keep changes focused, add provider-local regression tests for changed behavior,
and never add ROMs, save states, extracted assets, or recorded reference frames.

## Development

Install [uv](https://docs.astral.sh/uv/) and Rust (the repository pins its
toolchain), then clone and build the native extension:

```bash
git clone https://github.com/tsilva/env-BreakoutAtari2600-turbo-native.git breakout-native
cd breakout-native
uv sync --locked --extra dev --extra play
make develop-release
```

Run checks from the repository root:

```bash
uv run ruff check .
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo test --locked --lib
uv run pytest
```

Other useful commands after source setup:

```bash
uv run --frozen python examples/quickstart.py  # rollout and local timing
uv run --frozen --extra play env-breakoutatari2600-turbo-native play
uv run --frozen --extra play env-breakoutatari2600-turbo-native play --uncapped
make lint              # Python and Rust checks
make test              # Python and Rust tests
make develop-release   # rebuild the native extension after changes
```

Changes that can affect canonical `Start` behavior must also run:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data make parity
```

This thin command delegates cross-provider comparison to TurboBench's immutable
`breakout/start-v1` profile. It snapshots tracked changes and nonignored
untracked source, so committing first is unnecessary. Quick and checkout runs
are diagnostic.

Release certification runs against the exact final wheel:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data \
make parity-release \
  PARITY_WHEEL=/absolute/path/to/final.whl \
  PARITY_OUTPUT=/external/evidence/breakout-parity
```

The protected parity workflow owns lawful asset injection and publishes the
exact certified wheel with its self-verifying receipt. Provider-local tests may
check internal consistency, but cross-provider logic belongs in TurboBench.
