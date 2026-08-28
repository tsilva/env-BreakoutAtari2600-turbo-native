---
name: build-release
description: Prepare, build, approve, publish, and verify an env-breakoutatari2600-turbo-native release through its gated candidate state machine.
---

# Build Release

Use only the repository-owned release state machine. A release has three
reviewable transitions: prepared release commit, attested candidate, and
approved publication. Never create or push a release tag by hand, never
manually upload to PyPI, and never substitute a different workflow artifact
after candidate validation.

The binary release targets are exactly `macos-arm64` and `linux-x86_64`; the
candidate also contains a source distribution.

## Preconditions

Before beginning, verify all of these controls rather than assuming them:

- the legacy tag-triggered `Release` workflow remains disabled;
- the unprotected direct-push `main` workflow and the protected `pypi`
  environment match `docs/release-validation.md`;
- immutable GitHub Releases are enabled only after the pre-hardening evidence
  archive is verified in object-locked storage; and
- PyPI Trusted Publishing is restricted to
  `.github/workflows/release.yml` and the `pypi` environment; and
- one externally stored receipt from `make test-semantic-oracle` verifies for
  the exact release commit and version.

The release path does not require a self-hosted parity runner,
`PARITY_STABLE_RETRO_REPO`, release GitHub App secrets, or a tag ruleset.

If a retained precondition is absent, stop before publication and report it.
Do not weaken a retained gate to make progress.

## 1. Prepare the release commit

From a clean branch synchronized with its upstream:

```bash
UV_CACHE_DIR=.uv-cache uv sync --locked --extra dev
scripts/release.py prepare
```

Use `prepare --to <version>` or `prepare --part minor|major|patch` only when the
user explicitly chose that target. The command may modify only changelog and
version metadata. It never commits, tags, pushes, resolves dependencies, or
publishes. Review the diff, commit it directly on `main`, and push only after
the local checks pass.

From that clean release commit, generate the sole-oracle receipt. Store it
outside the checkout; no diagnostic command or pytest option can substitute:

```bash
RETRO_DATA_PATH=/path/to/lawful/stable_retro/data \
make test-semantic-oracle \
  STABLE_RETRO_TURBO_REPO=/path/to/env-StableRetro-turbo \
  ORACLE_CANDIDATE=checkout \
  ORACLE_RECEIPT=/external/evidence/stable-retro-turbo-oracle.json
```

The command must finish both receipt generation and its built-in verification.
Do not use `test-semantic-oracle-diagnostic`, `PYTEST_ARGS`, a dirty checkout,
or an unpinned provider as release evidence.

## 2. Build the attested candidate

After the release commit is pushed, capture the exact `main` SHA. Base64-encode
the sole-oracle receipt and dispatch `.github/workflows/release-build.yml` with
that exact SHA and the `oracle_receipt` input. The workflow verifies the receipt
against the SHA and version before source checks, embeds the receipt in the
candidate ledger, requires the SHA to remain current `main`, checks that the
PyPI version is unused, builds the candidate, and attests its provenance and
SBOM. Monitor it to completion and record its run id.

Do not rebuild a single artifact locally. If a build or audit fails, fix the
cause in a new direct `main` commit and build a new candidate for the new SHA.

## 3. Approve and publish

Dispatch `.github/workflows/release.yml` with the candidate run id,
version, and commit SHA. Inspect the candidate manifest, checksums, SBOM, and
attestation summaries before approving the `pypi` environment deployment.
Monitor through PyPI verification, tag creation, and GitHub Release creation.

The workflow may resume only when PyPI's complete file set is byte-identical to
the candidate. A partial or conflicting version is a hard stop.

## 4. Verify externally

Confirm the exact wheel and source filenames at:

```text
https://pypi.org/project/env-breakoutatari2600-turbo-native/<version>/
```

Then verify each downloaded distribution with:

```bash
gh attestation verify <distribution> --repo tsilva/env-BreakoutAtari2600-turbo-native
```

Confirm the `v<version>` tag resolves to the candidate SHA and the GitHub
Release contains all seven candidate files, including
`stable-retro-turbo-oracle.json`. Report the candidate and publish
workflow URLs in the final response.
