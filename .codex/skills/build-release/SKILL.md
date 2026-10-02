---
name: build-release
description: Prepare, certify, publish, and externally verify an env-breakoutatari2600-turbo-native release through its protected TurboBench and PyPI gates.
---

# Build release

Read and apply the shared `$release-workflow` skill at
`/Users/tsilva/.codex/skills/release-workflow/SKILL.md` before execution.
It owns common preflight, publication safeguards, `$push` integration,
workflow monitoring, verification, and reporting. The rules below are this
project's adapter; they retain its invocation default and required gates.
If the shared skill is unavailable, stop and report the missing dependency.

A bare `$build-release` or `/build-release` invocation authorizes the entire
release sequence: preparation, commit and push, parity certification, candidate
build and inspection, publication, and external verification. Complete it
automatically without asking for separate `oracle` or `pypi` approval. Retain
all validation gates and the PyPI wait timer. Explicitly local or inspection-only
requests do not advance publication transitions.

Use only the checked-in release state machine described in
`docs/release-validation.md`. Its reviewable transitions are:

1. a prepared release commit on `main`;
2. protected TurboBench parity evidence for that exact commit and final macOS
   wheel;
3. an attested cross-platform candidate bound to that parity run; and
4. automatic publication of the verified candidate through PyPI Trusted Publishing.

Never create or push a release tag by hand, upload to PyPI manually, rebuild a
single candidate artifact, or substitute an artifact from another run. The
supported binary targets are exactly `macos-arm64` and `linux-x86_64`; the
candidate also contains one source distribution.

## Preflight

Before changing release metadata:

- read `docs/release-validation.md` and the three workflow files named below;
- require the current branch to be named `main` and synchronized with
  `origin/main`; start clean, or resume only the previously prepared release
  metadata with `prepare --resume`;
- require authenticated `gh` access capable of dispatching workflows;
- confirm the legacy tag-triggered `Release` workflow is absent or disabled;
- confirm `.github/workflows/parity-evidence.yml`,
  `.github/workflows/release-build.yml`, and `.github/workflows/release.yml` are
  active;
- confirm the `oracle` environment has no required reviewers, remains restricted
  to `main`, and disallows administrator bypass;
- confirm the `pypi` environment has no required reviewers, remains restricted
  to `main`, disallows administrator bypass, and keeps its wait timer;
- confirm the publish workflow uses the `pypi` environment, OIDC
  `id-token: write`, and the pinned PyPI publish action without an API token;
  and
- confirm immutable GitHub Releases are enabled.

Apply the shared stop conditions if a retained control is absent or the
documentation and workflows disagree.

All compilation, dependency installation, Docker lock validation, native tests,
wheel builds, parity certification, candidate inspection, publication, and fresh
public-download verification run in GitHub Actions. The operator machine needs
only Python 3.11+ for standard-library metadata editing, Git, and authenticated
`gh`; never run `uv sync`, Cargo, maturin, or the release test suite locally for
this flow. The GitHub runners own their locked release environments.

## 1. Prepare the release commit

From the clean synchronized branch, run:

```bash
python3 scripts/release.py prepare
```

With no explicit target, `prepare` resolves the next patch version. Use
`prepare --to <version>` or `prepare --part minor|major|patch` only when the
user explicitly chose that target. This edits only changelog and version
metadata, checks version consistency, notes, lock policy, unused tag/PyPI
version, and preservation of the third-party dependency graph. It does not
compile or install the package. GitHub runs `scripts/release.py check` as a
mandatory dependency of parity certification and again for the candidate.

If an earlier preparation already wrote uncommitted metadata, review that diff
and use `python3 scripts/release.py prepare --resume`. Resume preserves the
prepared version and rejects unrelated edits or third-party lock changes.
Never bump again merely because a local preparation previously failed.

Review the diff before committing. Apply `$push` with scope limited to the
prepared metadata, capture the full `main` SHA, and require a clean worktree
with `HEAD == origin/main` before dispatching parity. Required remote checks
must succeed for this exact SHA before publication; a prepared commit alone
is not validation evidence.

## 2. Certify the exact macOS wheel

Dispatch the protected parity workflow for the full release SHA:

```bash
gh workflow run parity-evidence.yml -f ref="<40-character-release-sha>"
```

The `oracle` environment starts this job without manual approval. Monitor the
run to success and record its run id. If it unexpectedly waits for approval,
report the environment configuration mismatch rather than introducing a new
approval checkpoint.

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

Require the candidate workflow's `Inspect attested candidate before publication`
job to succeed. It downloads `release-candidate-v<version>` inside GitHub,
verifies the manifest identity and distribution checksums from `candidate/dist`,
and verifies provenance and SPDX attestations for every distribution against
`.github/workflows/release-build.yml` and the exact source SHA. Receipt validation
requires the official passed `breakout/start-v1` result for the pinned provider.

The inspected candidate contains exactly seven files recursively:

- `dist/<versioned-macos-arm64-wheel>`;
- `dist/<versioned-linux-x86_64-wheel>`;
- `dist/<versioned-source-archive>`;
- `SHA256SUMS`;
- `release-manifest.json`;
- `sbom.spdx.json`; and
- `turbobench-parity-receipt.tar.gz`.

No local build, package installation, or artifact substitution is needed to
inspect the candidate. Download its manifest for reporting when helpful.

If any build, audit, receipt, manifest, checksum, or attestation check fails,
stop. Fix the cause in a new commit, rerun parity for that SHA, and build a new
candidate.

## 4. Publish the verified candidate

After candidate inspection, dispatch:

```bash
gh workflow run release.yml \
  -f candidate_run_id="<candidate-run-id>" \
  -f version="<version>" \
  -f commit="<40-character-release-sha>"
```

The `pypi` environment releases the job automatically after its wait timer.
Invoking this skill already authorizes publishing the verified distributions
and creating the tag and immutable GitHub Release; do not request another
confirmation. If the run unexpectedly waits for manual review, report the
environment configuration mismatch. When the user has explicitly authorized
removing that requirement, approve an existing pending deployment through the
GitHub API and remove required reviewers while preserving the wait timer,
`main` restriction, and disabled administrator bypass.

Monitor through candidate revalidation, the idempotent PyPI
transition, exact PyPI file-set verification, protected tag creation, and
GitHub Release creation. A partial or conflicting PyPI version is a hard stop.

## 5. Verify externally

The publish workflow's `Verify fresh public release downloads` job runs
`scripts/verify_release.py` on a GitHub-hosted runner. Require that job and the
entire publish run to succeed. It downloads the exact three non-yanked PyPI
distributions, compares their SHA-256 values with the inspected candidate,
and verifies both provenance and SPDX attestations for every fresh download
against the candidate workflow and exact release SHA. It also verifies the
lightweight `v<version>` tag and fresh copies of all seven assets from the
published immutable GitHub Release.

Download `release-verification-v<version>` from the publish run. Check its
`verification.json` binds the expected version, tag, full release SHA and
candidate run id, and records `verified: true`. A verification failure after
publication is an incomplete release; preserve the published version, report
the failed gate, and do not repeat publication or substitute distributions.

Finish only after the worktree is clean and synchronized. Report the PyPI and
GitHub Release links, tag and SHA, distribution filenames, and parity,
candidate, and publish workflow URLs. GradLab updates begin only after the
remote external-verification job passes.

## Update GradLab after successful publication

After the release succeeds and the exact PyPI version and required GitHub
Release artifacts pass external verification, update GradLab to consume the
latest successfully published `env-breakoutatari2600-turbo-native` version. Complete
this step as part of the full publication flow; local builds, dry runs, and
inspection-only requests do not trigger it.

Read `/Users/tsilva/repos/tsilva/gradlab/AGENTS.md` and its required
specifications before editing. Synchronize GradLab's current branch with its
configured upstream and preserve existing work. Update every matching exact
pin in `pyproject.toml`, including platform-specific project dependencies and
the `train-runtime` dependency group. Use the just-verified release version;
if GradLab already consumes a newer verified publication, do not downgrade it.
Regenerate `uv.lock` with `uv lock --upgrade-package env-breakoutatari2600-turbo-native`,
preserving unrelated pins, supply-chain constraints, and existing per-package
release-age exceptions. Review the dependency diff, validate lock consistency,
and run GradLab's relevant provider compatibility checks.

Report the GradLab version/pin and lockfile update separately from release
success. If synchronization, resolution, or validation fails, preserve the
published release and report the downstream update as incomplete with its
blocker; do not repeat publication.
