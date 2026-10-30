# env-BreakoutAtari2600-turbo-native Codex Notes

## Product Specifications

When specifications exist, use `$specs-author` for substantive work and
specification changes. Follow its shared read/reuse cadence, provisional-scenario
guidance, proportional detail, decision-based approval, and closing intent check.
The maintained procedure is `/Users/tsilva/.codex/skills/private-skills/specs-author/SKILL.md`.

- Use `/breakout-native_build-release` to cut, tag, publish, and verify PyPI releases with
  validated macOS arm64 and Linux x86_64 wheels. Skill:
  `.codex/skills/breakout-native_build-release/SKILL.md`.

## Agent skills

### Issue tracker

Issues and specs are tracked in this repository’s GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository with a root `CONTEXT.md`. See `docs/agents/domain.md`.

## Shared release procedure

The project `breakout-native_build-release` skill composes `$release-workflow` from
`/Users/tsilva/.codex/skills/release-workflow/SKILL.md`.
Read both for release work; keep project commands, version policy, artifact
requirements, and approval gates in the project adapter.

## Benchmark publication

- Keep README benchmark prose to one link to root `benchmarks.md` beside the current media and chart.
- Update `benchmarks.md` with the latest benchmark's results, hardware, method, policy, limitations, asset provenance, pinned verification instructions, and proof links whenever publishing a benchmark. Replace superseded benchmark prose; retain older runs only as proof references.
- Keep the linked report consistent with the README assets and `demo-manifest.json`; preserve immutable proof archives and their version-specific verification instructions.

## Benchmark infrastructure privacy

Never publish or print benchmark machine hostnames, IP addresses, ports, SSH aliases, login names, private tracking URLs, or other machine access/location details. Report hardware specifications only. Keep proofs containing access details private and omit their public download links.
