# Release validation

This repository owns provider-local checks. Cross-provider behavior is certified
by TurboBench's immutable `breakout/start-v1` profile against original
`stable-retro==1.0.1`. The [v0.5.15 parity receipt](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/download/v0.5.15/turbobench-parity-receipt.tar.gz)
certifies canonical `Start` behavior for its exact final wheel; it measures
neither throughput nor equivalence with the Arcade Learning Environment.

Parity covers exact observations, frames, rewards, lifecycle, resets, selected
info including `ball_y`, snapshot continuation, and the seeded noop-reset
distribution. Development `make parity` runs snapshot the worktree and remain
diagnostic. Exact-wheel certification uses:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data \
make parity-release \
  PARITY_WHEEL=/absolute/path/to/final.whl \
  PARITY_OUTPUT=/external/evidence/breakout-parity
```

Parity requires a separately obtained lawful ROM; normal use needs none.
The protected workflow obtains it according to `validation/parity-assets.json`
and removes it afterward. Private assets and local paths must not enter receipts
or distributions; packages contain no ROMs, provider save states, recorded
reference frames, or extracted game assets.

## Release gates

Use the [build-release skill](../.codex/skills/build-release/SKILL.md) for the
release procedure. Local `python3 scripts/release.py prepare` uses the standard
library to validate metadata, release notes, lock policy, an unused version/tag,
and unchanged third-party dependencies. `prepare --resume` accepts an already
prepared uncommitted version, rejecting unrelated changes. Builds and native
checks run in GitHub Actions; local compilation is unnecessary.

| Phase | Required evidence |
| --- | --- |
| Parity (`parity-evidence.yml`) | Ubuntu `scripts/release.py check` passes lock consistency, lint, Rust checks/tests, native compilation, and Python tests before protected macOS certification. The canonical-host wheel is built once, certified by TurboBench, and attested with a verified receipt. |
| Candidate (`release-build.yml`) | Source is revalidated and the same certified wheel is reused. Inspection verifies the seven-file manifest, distribution checksums, and provenance and SPDX attestations. |
| Publication | Candidate and both attestation types are revalidated before the protected five-minute PyPI wait timer, tag creation, and immutable GitHub Release. |
| External verification | Independently download all public PyPI distributions and seven GitHub assets; compare hashes, verify both PyPI attestation types and exact tag SHA, and record `release-verification-v<version>/verification.json`. |

A release is complete only after external verification passes. GradLab updates
follow that evidence.

## Evidence ownership

Root [SPECS.md](../SPECS.md) is authoritative. Maintained evidence belongs to:

- API, lifecycle, physics, reset RNG, rendering, snapshots, and trace consistency:
  `tests/`, `src/`, and `scripts/deterministic_trace.py`.
- Supported-host wheels and release consistency: release workflows and
  `scripts/release_state.py`.
- Cross-provider parity: TurboBench's `breakout/start-v1`, invoked through thin
  Make targets and the protected parity workflow.
- Private-asset exclusion: package manifests, release audits, and
  `validation/parity-assets.json` used only by the protected workflow.

## Performance evidence

See [benchmarks.md](../benchmarks.md) for the latest benchmark, method,
limitations, pinned verifier instructions, and current and earlier proof files.
Benchmark and showcase evidence does not replace the library release's canonical
`breakout/start-v1` parity receipt.
