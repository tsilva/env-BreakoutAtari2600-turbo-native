## Outcome

Describe the user-visible result and why it belongs in env-BreakoutAtari2600-turbo-native.

## Validation

- [ ] `uv run ruff check .`
- [ ] `cargo fmt --check`
- [ ] `cargo clippy --all-targets -- -D warnings`
- [ ] `cargo test --lib`
- [ ] `uv run pytest -m "not stable_retro"`
- [ ] Pinned Stable Retro Turbo sole-oracle run, or not applicable:
  `RETRO_DATA_PATH=/path/to/lawful/stable_retro/data make test-semantic-oracle`

## Compatibility and provenance

- [ ] I documented any public API, snapshot, or behavior change.
- [ ] I did not add a ROM, save state, extracted game asset, or unlicensed material.
- [ ] The change preserves the supported platform boundary.
