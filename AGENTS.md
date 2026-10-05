# env-BreakoutAtari2600-turbo-native Codex Notes

## Product Specifications

Before every task in this repository, use the `$specs-author` skill to read the entire root `SPECS.md`. Before finishing, reread it and check the task and conversation for new or changed stakeholder intent.

- Treat `SPECS.md` as the persistent source of stakeholder requirements that cannot be inferred reliably from code or remembered conversations.
- Apply the scope test to proposed and existing requirements: root `SPECS.md` contains only project-wide intent; scoped intent belongs in its nearest authoritative specification and must not be broadened to fit the root.
- If the task, repository, or user request contradicts, omits, or ambiguously interprets the specification, tell the user. Continue safe exploration and work that does not depend on resolving the issue, but never silently choose an interpretation.
- Never edit `SPECS.md` from inference. Propose the exact change, explain why it reflects stakeholder intent, and edit the file only after the user explicitly approves that exact change.
- Keep `SPECS.md` complete, concise, and compacted. It must contain stakeholder intent rather than implementation, architecture, operations, or transient project detail.

- Use `/build-release` to cut, tag, publish, and verify PyPI releases with
  validated macOS arm64 and Linux x86_64 wheels. Skill:
  `.codex/skills/build-release/SKILL.md`.

## Agent skills

### Issue tracker

Issues and specs are tracked in this repository’s GitHub Issues. See `docs/agents/issue-tracker.md`.

### Domain docs

This is a single-context repository with a root `CONTEXT.md`. See `docs/agents/domain.md`.

## Shared release procedure

The project `build-release` skill composes `$release-workflow` from
`/Users/tsilva/.codex/skills/release-workflow/SKILL.md`.
Read both for release work; keep project commands, version policy, artifact
requirements, and approval gates in the project adapter.

## Benchmark publication

- Keep README benchmark prose to one link to root `benchmarks.md` beside the current media and chart.
- Update `benchmarks.md` with the latest benchmark's results, hardware, method, policy, limitations, asset provenance, pinned verification instructions, and proof links whenever publishing a benchmark. Replace superseded benchmark prose; retain older runs only as proof references.
- Keep the linked report consistent with the README assets and `demo-manifest.json`; preserve immutable proof archives and their version-specific verification instructions.
