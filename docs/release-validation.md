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

Before building a release candidate, generate the sole pinned Stable Retro
Turbo receipt from a clean candidate checkout through its public
vector-provider API:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data \
make test-semantic-oracle \
  STABLE_RETRO_TURBO_REPO=/path/to/env-StableRetro-turbo \
  ORACLE_CANDIDATE=checkout \
  ORACLE_RECEIPT=/external/evidence/stable-retro-turbo-oracle.json
```

[`validation/stable-retro-turbo.json`](../validation/stable-retro-turbo.json)
is the single operational pin: it binds the provider commit and tree. The
certifying environment uses native Python 3.14, builds its provider wheel only
from a disposable clone of that clean detached tree, validates the installed
source files and RECORD ledger, and records the wheel digest. It builds the
checkout candidate in a separate isolated environment, then
executes the fixed 2,048-step cycling and
seeded-random trajectories plus seeded-reset semantics and distributions for
the canonical one-lane and multi-lane workloads. Its receipt binds the exact
provider pin, candidate version and commit, workload, environment
configuration, and exact comparison result.

The command fails closed if the pinned provider, Turbo Vector API, lawful ROM,
clean candidate, candidate identity, complete fixed workload, or trajectory
result is missing or incompatible. It has no pytest passthrough, so diagnostic
options such as `--collect-only` cannot create evidence. The configurable
`make test-semantic-oracle-diagnostic PYTEST_ARGS=...` target is explicitly
non-certifying. An unpinned or modified provider checkout can be useful there,
but it cannot satisfy the release command.

To validate the exact immutable package-index candidate instead, run the same
command in a clean source checkout with `ORACLE_CANDIDATE=X.Y.Z` and
`ORACLE_CANDIDATE_COMMIT=<40-character-source-SHA>`. The command installs that
published distribution into its isolated candidate environment and rejects a
local path or sibling-checkout substitution.

Release authority comes only from the protected manual `Stable Retro Turbo
oracle evidence` workflow. Its `oracle` environment supplies bucket-scoped,
read-only Cloudflare R2 credentials as `R2_ACCESS_KEY_ID` and
`R2_SECRET_ACCESS_KEY`, plus the non-secret `R2_ACCOUNT_ID` and `R2_BUCKET`
variables. The private bucket remains the external source of the separately and
lawfully obtained ROM. [`validation/oracle-roms.json`](../validation/oracle-roms.json)
binds each supported game to its generic bucket object key, byte size, and
SHA-256 digest. The workflow checks out the exact current `main` commit,
downloads only that object into runner-temporary storage, rejects a digest or
size mismatch, fetches the content-pinned provider, runs the same canonical
command, deletes the ROM and provider checkout, and creates GitHub build
provenance for the resulting receipt. It accepts no caller-provided report or
receipt JSON:

```bash
gh workflow run oracle-evidence.yml -f ref="$(git rev-parse HEAD)"
gh run watch <oracle-run-id> --exit-status
gh workflow run release-build.yml \
  -f ref="$(git rev-parse HEAD)" -f oracle_run_id=<oracle-run-id>
```

The candidate workflow requires that exact successful workflow path, event,
head SHA, artifact, and GitHub provenance from the oracle workflow at that
source commit on a GitHub-hosted runner before it verifies the receipt,
embeds it in the candidate ledger, and allows publication to verify it again.
Duplicate-key JSON is rejected. Ordinary public CI cannot generate this
private-ROM evidence; only the protected manual workflow can access the lawful
ROM. The receipt contains no ROM, frame, save state, or provider package.

The R2 bucket is private and reusable for other lawful ROMs. Add another object
under a system/game-specific key and pin it in `validation/oracle-roms.json`;
never enable the managed public domain or a custom public domain. R2 credentials
belong only in the protected `oracle` environment. The workflow never caches or
uploads a ROM, and GitHub decommissions the hosted runner after the job.

## Candidate artifacts

Each candidate contains exactly:

- CPython 3.11+ ABI3, macOS 11+, ARM64 wheel;
- CPython 3.11+ ABI3, manylinux glibc 2.28+, x86-64 wheel;
- source archive;
- `SHA256SUMS`;
- `release-manifest.json`;
- `stable-retro-turbo-oracle.json`; and
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
does not require a self-hosted parity runner, a Stable Retro Turbo repository
variable, GitHub App secrets, or a tag ruleset.

PyPI remains OIDC-only. Never add an API token or use a manual upload as a
shortcut around a failed gate.
