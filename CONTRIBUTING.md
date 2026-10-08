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

Run checks and try the environment from the repository root:

```bash
make lint              # Python and Rust checks
make test              # Python and Rust tests
uv run --frozen python examples/quickstart.py  # rollout and local timing
uv run --frozen --extra play env-breakoutatari2600-turbo-native play
uv run --frozen --extra play env-breakoutatari2600-turbo-native play --uncapped
```

Rebuild with `make develop-release` after native changes. Changes that can
affect canonical `Start` behavior must also run:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data make parity
```

This diagnostic delegates comparison to TurboBench's immutable
`breakout/start-v1` profile using a snapshot of tracked changes and nonignored
untracked source; committing first is unnecessary. Cross-provider comparison
logic belongs in TurboBench. See [release validation](docs/release-validation.md)
for exact-wheel certification and required release evidence.
