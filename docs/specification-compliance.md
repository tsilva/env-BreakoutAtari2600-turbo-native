# Specification compliance

The root `SPECS.md` is authoritative. Maintained evidence is split by owner:

- public API, lifecycle, physics, reset RNG, renderer, snapshots, and trace
  consistency: `tests/`, `src/`, and `scripts/deterministic_trace.py`;
- supported-host wheel and release consistency: the release workflows and
  `scripts/release_state.py`;
- cross-provider parity: TurboBench profile `breakout/start-v1`, invoked only
  through the thin Make targets and protected parity workflow;
- private-asset exclusion: package manifests, release audits, and
  `validation/parity-assets.json` used only by the protected workflow.

The former repository-local comparator and authority-specific receipt code were
removed. This repository does not implement a second cross-provider standard.
