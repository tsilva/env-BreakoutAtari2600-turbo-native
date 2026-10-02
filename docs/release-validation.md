# Release validation

Provider unit, Rust, deterministic trace, wheel smoke, and supported-host
checks are owned by this repository and execute in GitHub Actions for releases. Cross-provider behavior is certified by
TurboBench's immutable `breakout/start-v1` profile against original
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

Invoking `/build-release` authorizes the complete release procedure, including
committing and pushing prepared metadata, parity certification, candidate
preparation and inspection, publication, and external verification. It runs
without further approval prompts. Both `oracle` and `pypi` environments remain
restricted to `main`, have no required reviewers, and disallow administrator
bypass. PyPI publication retains its wait timer, and all validation gates remain
mandatory.

```bash
gh workflow run parity-evidence.yml -f ref="$(git rev-parse HEAD)"
gh run watch <parity-run-id> --exit-status
gh workflow run release-build.yml \
  -f ref="$(git rev-parse HEAD)" -f parity_run_id=<parity-run-id>
```

The ROM is fetched from protected storage according to
`validation/parity-assets.json`. No private asset or local path enters the
portable receipt or release distribution.

## Execution boundary

Local `python3 scripts/release.py prepare` uses only the Python standard library
to prepare metadata and verify its consistency, release notes, lock policy,
unused version/tag, and unchanged third-party dependency graph. The operator
reviews and pushes the metadata, then dispatches and monitors the workflows.
No local Rust, Docker, `uv sync`, package build, or native test is required.
Use `prepare --resume` to validate an already prepared uncommitted version;
resume rejects unrelated files and third-party dependency changes.

The parity workflow first runs `scripts/release.py check` on Ubuntu, including
Docker lock consistency, lint, Rust checks/tests, native compilation, and Python
tests. Only after those checks pass can the protected macOS wheel certification
start. The candidate revalidates the source and reuses the certified macOS
wheel. Its final inspection job verifies the seven-file manifest, distribution
checksums, and both provenance and SPDX attestations before publication.

The publish workflow revalidates the candidate and both attestation types,
retains the protected five-minute PyPI wait timer, and creates the tag and
immutable GitHub Release. Its final verification job independently downloads
all public PyPI distributions and all seven GitHub assets, compares hashes,
verifies both PyPI distribution attestation types and the exact tag SHA, and
records `release-verification-v<version>/verification.json`. A release is
complete only when this job passes; GradLab updates follow that evidence.
