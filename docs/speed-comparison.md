# Breakout speed comparison

[Watch the 720p MP4](../media/speed-comparison/comparison.mp4) or
[view the animated preview](../media/speed-comparison/comparison.gif).

This October 1, 2026 comparison uses the published macOS arm64 wheels of
`env-breakoutatari2600-turbo-native==0.5.13` and `stable-retro==1.0.1` on an
Apple M1 Pro with eight logical CPUs, 16 GiB RAM, and CPython 3.14.5.
TurboBench `2.0.7` ran the immutable `breakout/start-v1` workload using its
phase-isolated execution protocol.

**This is a diagnostic preview, not a validated performance claim.** The
Mac exceeded TurboBench's system-load threshold, so timing used `--force-busy`.
The video retains a prominent diagnostic header. An attempted Linux run also
failed the rendered-frame and observation checks; its timing is not used here.

## What the animation shows

The left panel replays original Stable Retro at a 60-frame-per-second baseline.
The right panel replays native Breakout faster by the measured one-lane paired
throughput ratio, then holds its final frame. Both use exactly the same 1,800
actions and 1,801 rendered frames, including the initial frame. The replay
matched exactly, with zero mismatches. It is a fixed action trajectory, not a
trained policy.

Playback illustrates relative throughput; it is not a screen recording of
either provider's execution time. Benchmark steps advance four native frames
and produce four stacked grayscale 84×84 policy observations. Replay uses one
native frame per step so the animation can show the entire trajectory.

| Lanes | Native median transitions/s | Stable Retro median transitions/s | Paired ratio | Paired 95% CI |
| ---: | ---: | ---: | ---: | :---: |
| 1 | 34,436.6 | 773.5 | 45.0552× | [36.4204, 45.8494] |
| 16 | 130,341.4 | 2,941.8 | 42.0406× | [41.6233, 52.0270] |
| 32 | 104,350.5 | 2,958.7 | 34.4495× | [28.5921, 38.0576] |

These are busy-host diagnostic measurements. Each lane count used one warmup
pair, seven alternating measurement pairs, and three repetitions per invocation.
Timing includes stepping, observation preprocessing, IPC, information values,
terminal detection, and selective resets. Rendering and encoding are excluded.
The video uses only the one-lane ratio; ratios are not aggregated across shapes.

## Verification evidence

Matched correctness checks passed at 1, 16, and 32 lanes. The replay check
also passed, and the complete bundle passed TurboBench integrity verification.
Integrity verification does not make the diagnostic timings an official claim.

- [Generated benchmark report](../media/speed-comparison/benchmark-report.md)
- [Media manifest and output hashes](../media/speed-comparison/media-manifest.json)
- [Complete portable evidence bundle](../media/speed-comparison/benchmark.tar.gz)

The archive contains exact provider artifact identities, the workload, timing
samples, correctness and replay hashes, contract attestations, reports, and
media. It contains no ROM, provider save state, or raw reference frames.
The media manifest records a presentation cleanup that removes fragments of
an obscured duplicate watermark between panels; the full diagnostic header,
gameplay, labels, and relative timing are retained. The original encoded MP4
is preserved in the archive.

The bundle ID is
`753a371000642961c76866c18a5efff1aa632f77c90faf4dea285e4cf084a6e0`.
The TurboBench source commit was
`5d79063ab8bbfa32e1a85d5a385f041ef842bd44`; its harness source hash is recorded
in the bundle. To verify after extraction, run from this repository's root:

```bash
mkdir -p /tmp/breakout-speed-evidence
tar -xzf media/speed-comparison/benchmark.tar.gz -C /tmp/breakout-speed-evidence
uv run --directory ../turbobench --frozen turbobench verify /tmp/breakout-speed-evidence/benchmark
```

## Refreshing the comparison

Run the same profile on an idle Mac with the matching lawful assets configured.
Use a fresh output directory and no diagnostic overrides:

```bash
uv run --directory ../turbobench --frozen turbobench compare breakout/start-v1 \
  --left env-breakoutatari2600-turbo-native@0.5.13 \
  --right stable-retro@1.0.1 \
  --promo \
  --output /tmp/breakout-speed-verified
```

Replace the preview only after benchmark validity, matched replay, media
validation, and bundle verification pass. Keep comparison logic in TurboBench.
