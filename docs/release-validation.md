# Release validation

Releases use two isolated workflows. No pushed tag can publish a package.
Every transition is tied to one final version and one full commit SHA.

1. `Release candidate` requires the candidate to be the current `main` commit,
   builds the exact supported distributions, smoke-installs them on Python 3.11
   and 3.14, creates an SPDX SBOM and content-addressed manifest, and signs
   GitHub build-provenance and SBOM attestations.
2. `Publish approved release` downloads one named candidate run, revalidates
   its commit, file set, sizes, SHA-256 values, and GitHub attestations, then
   waits behind the protected `pypi` environment. Only the exact candidate may
   be sent through PyPI Trusted Publishing. The workflow's scoped GitHub token
   creates the tag and GitHub Release after PyPI verification.

The state machine rejects a reused version unless PyPI already contains the
complete, byte-identical candidate. This permits safe recovery after a
post-upload interruption without enabling replacement or partial releases.

## Prepare a release commit

Use the repository command from clean, synchronized `main`:

```bash
uv sync --locked --extra dev
scripts/release.py prepare
```

The command promotes human-authored changelog notes and updates only the
version metadata files. It does not commit, tag, push, regenerate dependency
graphs, or publish. Dependency changes belong in a separate commit.

Local and CI checks use the committed locks and pinned Rust toolchain:

```bash
python scripts/lock.py
cargo fmt --check
cargo clippy --locked --all-targets -- -D warnings
cargo check --locked --release
cargo test --locked --lib
pytest -m "not stable_retro"
```

## Supported-platform determinism evidence

Every CI run generates the same ROM-free public lane trace independently on
Apple-silicon macOS and x86-64 Linux. Each generator first proves that its
target lane is unchanged by batch size, active neighboring lanes, lane order,
or thread count. The workload records reset and transition observations,
rewards, termination and truncation flags, shared information, and exact
continuation from a serialized snapshot.

The two jobs upload fresh JSON traces for that run. A dependent job downloads
both artifacts and compares them with:

```bash
python scripts/deterministic_trace.py compare \
  deterministic-trace-macos-arm64.json \
  deterministic-trace-linux-x86_64.json
```

The command accepts exactly one trace from each supported binary platform and
requires the package version and workload identity to agree. A mismatch names
both platforms and the first divergent public trace field. Observation
mismatches include the exact CHW element and both `uint8` values. No expected
digest, recorded frame, or other oracle trace is checked into the repository.

Before publishing, a clean candidate checkout must pass the sole pinned Stable
Retro Turbo semantic oracle through its public vector-provider API:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data \
make test-semantic-oracle \
  STABLE_RETRO_TURBO_REPO=/path/to/env-StableRetro-turbo
```

[`validation/stable-retro-turbo.json`](../validation/stable-retro-turbo.json)
is the single operational pin. Validation fails closed if the exact checkout,
reported provider version, Turbo Vector API, or lawful ROM is absent or
incompatible. Public CI cannot run this private-ROM check; its ordinary tests
validate the harness and environment contracts but are not cartridge-fidelity
evidence.

## Candidate artifacts

Each candidate contains exactly:

- CPython 3.11+ ABI3, macOS 11+, ARM64 wheel;
- CPython 3.11+ ABI3, manylinux glibc 2.28+, x86-64 wheel;
- source archive;
- `SHA256SUMS`;
- `release-manifest.json`; and
- `sbom.spdx.json`.

Linux wheels are built with `Cargo.lock --locked` inside a digest-pinned
official maturin image. The old network-fetched Rust installer is not used.
The source archive is available for inspection and reproducible builds but
does not extend the supported platform set.

## Repository controls

`main` intentionally permits direct maintainer pushes and does not require pull
requests or status checks. CI, package tests, dependency review, and CodeQL
still run as detection and feedback. Release publication remains separate: the
`pypi` environment accepts only the `main` branch, has a wait timer and required
approval, and disallows administrator bypass.

The publish workflow uses its repository-scoped `GITHUB_TOKEN` with
`contents: write` to create the exact `v<version>` tag and GitHub Release. It
does not require a self-hosted parity runner, a Stable Retro repository
variable, GitHub App secrets, or a tag ruleset.

PyPI remains OIDC-only. Never add an API token or use a manual upload as a
shortcut around a failed gate.
