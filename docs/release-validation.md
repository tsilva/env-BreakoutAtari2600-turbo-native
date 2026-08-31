# Release validation

Provider-local unit, Rust, deterministic trace, wheel smoke, and supported-host
checks remain in this repository. Cross-provider behavior is certified by
TurboBench's immutable `breakout/start-v2` profile against original
`stable-retro==1.0.1`.

During development, run `make parity` with a lawful `RETRO_DATA_PATH`. The
command tests an isolated snapshot of the current worktree and is always
diagnostic. It covers exact observations, frames, rewards, lifecycle, resets,
selected info including `ball_y`, continuation after snapshots, and the seeded
noop-reset distribution.

The protected `.github/workflows/parity-evidence.yml` workflow builds the
canonical-host wheel once, passes that exact wheel to TurboBench, verifies the
receipt, attests the wheel, and removes the private ROM. The release candidate
reuses that same wheel; it does not certify a checkout or rebuild.

```bash
gh workflow run parity-evidence.yml -f ref="$(git rev-parse HEAD)"
gh run watch <parity-run-id> --exit-status
gh workflow run release-build.yml \
  -f ref="$(git rev-parse HEAD)" -f parity_run_id=<parity-run-id>
```

The ROM is fetched from protected storage according to
`validation/parity-assets.json`. No private asset or local path enters the
portable receipt or release distribution.
