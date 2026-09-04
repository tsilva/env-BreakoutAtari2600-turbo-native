---
name: build-release
description: Prepare, certify, publish, and externally verify an env-breakoutatari2600-turbo-native release through its protected TurboBench and PyPI gates.
---

# Build release

Use only the checked-in release state machine described in
`docs/release-validation.md`. Its reviewable transitions are:

1. a prepared release commit on `main`;
2. protected TurboBench parity evidence for that exact commit and final macOS
   wheel;
3. an attested cross-platform candidate bound to that parity run; and
4. separately approved publication through PyPI Trusted Publishing.

Never create or push a release tag by hand, upload to PyPI manually, rebuild a
single candidate artifact, or substitute an artifact from another run. The
supported binary targets are exactly `macos-arm64` and `linux-x86_64`; the
candidate also contains one source distribution.

## Preflight

Before changing release metadata:

- read `docs/release-validation.md` and the three workflow files named below;
- require the current branch to be clean, named `main`, and synchronized with
  `origin/main`;
- require authenticated `gh` access capable of dispatching workflows;
- confirm the legacy tag-triggered `Release` workflow is absent or disabled;
- confirm `.github/workflows/parity-evidence.yml`,
  `.github/workflows/release-build.yml`, and `.github/workflows/release.yml` are
  active;
- confirm the `oracle` and `pypi` environments retain required reviewers,
  disallow administrator bypass, and keep the `pypi` wait timer;
- confirm the publish workflow uses the `pypi` environment, OIDC
  `id-token: write`, and the pinned PyPI publish action without an API token;
  and
- confirm immutable GitHub Releases are enabled.

If a retained control is absent or the documentation and workflows disagree,
stop before publication. Do not weaken a gate to make progress.

The lock validator uses Docker, so require a working Docker daemon before
running release preparation. Isolate local `uv` from user-wide configuration;
otherwise global `exclude-newer-package` exemptions can make the committed
lock appear stale even when the repository-owned lock policy is valid:

```bash
release_xdg_config="$(mktemp -d)"
env -u UV_CONFIG_FILE -u UV_NO_CONFIG \
  XDG_CONFIG_HOME="$release_xdg_config" \
  UV_CACHE_DIR=.uv-cache \
  uv sync --locked --extra dev
```

## 1. Prepare the release commit

From the clean synchronized branch, run:

```bash
UV_CACHE_DIR=.uv-cache scripts/release.py prepare
```

With no explicit target, `prepare` resolves the next patch version. Use
`prepare --to <version>` or `prepare --part minor|major|patch` only when the
user explicitly chose that target. The command may modify only changelog and
version metadata and must run its complete local release checks.

Review the diff before committing. Commit and push the prepared metadata only
when authorized by the release request. Capture the resulting full `main` SHA
and require both a clean worktree and `HEAD == origin/main` before continuing.

If preparation stops after writing metadata, fix the prerequisite and run the
remaining repository-owned checks exactly; do not bypass a failed check or
silently regenerate the dependency graph.

## 2. Certify the exact macOS wheel

Dispatch the protected parity workflow for the full release SHA:

```bash
gh workflow run parity-evidence.yml -f ref="<40-character-release-sha>"
```

When the run waits on the `oracle` environment, ask the user for approval at
that checkpoint. Do not approve it from a prior or implied authorization.
Monitor the run to success and record its run id.

The workflow must be `.github/workflows/parity-evidence.yml`, be a
`workflow_dispatch` run at the exact release SHA, and produce
`breakout-parity-<sha>`. It builds the final macOS wheel once, certifies that
exact wheel with TurboBench's immutable `breakout/start-v1` profile, verifies
the receipt, removes the lawful private ROM, and provenance-attests the wheel.
Do not use local, quick, dirty, shortened, or overridden parity as release
evidence.

## 3. Build and inspect the candidate

Dispatch the candidate workflow with the same SHA and successful parity run:

```bash
gh workflow run release-build.yml \
  -f ref="<40-character-release-sha>" \
  -f parity_run_id="<parity-run-id>"
```

Monitor it to success and record its run id. The workflow must reuse the
parity-certified macOS wheel, build and smoke-test the Linux wheel and source
distribution, verify the parity receipt, audit the distributions, generate an
SPDX SBOM, and attest both provenance and SBOM.

Download `release-candidate-v<version>` and inspect it before publication. It
must contain exactly seven files when counted recursively:

- `dist/<versioned-macos-arm64-wheel>`;
- `dist/<versioned-linux-x86_64-wheel>`;
- `dist/<versioned-source-archive>`;
- `SHA256SUMS`;
- `release-manifest.json`;
- `sbom.spdx.json`; and
- `turbobench-parity-receipt.tar.gz`.

Verify the distribution checksums from inside `candidate/dist`, require the
manifest to bind the expected package, version, release SHA, repository, and
candidate run id, and require the portable TurboBench result to be official
and passed for the pinned profile and provider. Verify each distribution's
provenance and SPDX attestations against
`.github/workflows/release-build.yml` and the exact source SHA.

If any build, audit, receipt, manifest, checksum, or attestation check fails,
stop. Fix the cause in a new commit, rerun parity for that SHA, and build a new
candidate.

## 4. Approve and publish

After candidate inspection, dispatch:

```bash
gh workflow run release.yml \
  -f candidate_run_id="<candidate-run-id>" \
  -f version="<version>" \
  -f commit="<40-character-release-sha>"
```

When the run waits on the `pypi` environment, explain that approval will
publish the distributions and create the tag and immutable GitHub Release.
Require a new explicit user approval for this publication checkpoint; the
earlier `oracle` approval does not carry over.

After approval, monitor through candidate revalidation, the idempotent PyPI
transition, exact PyPI file-set verification, protected tag creation, and
GitHub Release creation. A partial or conflicting PyPI version is a hard stop.

## 5. Verify externally

Use fresh downloads from:

```text
https://pypi.org/project/env-breakoutatari2600-turbo-native/<version>/
```

Require exactly the two supported wheels and one source distribution. Compare
their SHA-256 values with the inspected candidate, then verify both attestation
types for every downloaded distribution:

```bash
gh attestation verify <distribution> \
  --repo tsilva/env-BreakoutAtari2600-turbo-native \
  --signer-workflow tsilva/env-BreakoutAtari2600-turbo-native/.github/workflows/release-build.yml \
  --source-digest <40-character-release-sha> \
  --deny-self-hosted-runners

gh attestation verify <distribution> \
  --repo tsilva/env-BreakoutAtari2600-turbo-native \
  --predicate-type https://spdx.dev/Document \
  --signer-workflow tsilva/env-BreakoutAtari2600-turbo-native/.github/workflows/release-build.yml \
  --source-digest <40-character-release-sha> \
  --deny-self-hosted-runners
```

Confirm `v<version>` resolves to the release SHA and the immutable GitHub
Release contains the same seven files, including
`turbobench-parity-receipt.tar.gz`. Finish only after the worktree is clean and
synchronized. Report the PyPI and GitHub Release links, tag and SHA, artifact
filenames, and parity, candidate, and publish workflow URLs.
