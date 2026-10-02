# Trained-policy speed comparison

[Watch the comparison](../media/speed-comparison/comparison.mp4),
[view the animated preview](../media/speed-comparison/comparison.gif), or
[watch the full native-policy episode](../media/speed-comparison/full-policy.mp4).

The comparison uses GradLab's final FirstWall PPO checkpoint, trained for
191,561,728 steps. GradLab played the policy through its verified artifact
loader with the recorded training contract, stochastic sampling at temperature
1, the recorded auto-serve rule, and playback seed 1,000,000. The first attempt
cleared all 108 bricks: Atari score 432, three lives remaining, and GradLab
task outcome `SUCCESS` after 4,139 policy decisions. This playback does not
establish a success rate or promotion decision.

The checkpoint belongs to run `gradlab-2ab417e09bfa4a0c1946070089b23fe0`, with
checkpoint ID `checkpoint-191561728-dcfd8a41bcc7426a`. Its SHA-256 is
`dcfd8a41bcc7426ac0ef2f108d07a20f2ffb2c0c22745e6690c6065c01d5935a`.
Open the training run in MLflow (run `e10b9f9dfec247b881d2eac3979dda37`).
Model loading, task semantics, and inference remain in GradLab; provider replay
and comparison rendering use TurboBench outside this repository.

## What the comparison shows

The left panel is labeled `Stable Retro 1.0.1`; the right is labeled
`BreakoutAtari2600-turbo 0.5.13`, referring to the published native package.
Both replay the same recorded effective actions, including
auto-serve overrides. The recording begins with the policy's 21 raw-frame reset
noops. Each policy decision then supplies two identical raw-frame actions,
matching the checkpoint's frame skip of two.

The comparison contains the exactly matching first 2,946 policy decisions:
5,913 raw-frame actions and 5,914 frames including the initial frame. Every
frame, replay observation, reward, terminal flag, and selected information
value matches across providers. It ends at score 429 with four lives and three
bricks remaining. This is an excerpt, not a completed wall.

Both panels are compressed by a common factor of four. Stable Retro therefore
plays at 4× game speed, and native plays at 140.5215×, preserving the diagnostic
relative throughput ratio of 35.1304×. The faster panel holds its final frame; both videos include a two-second end hold.
The comparison lasts about 26.65 seconds. The separate full native-policy video
plays the complete episode at 4× in about 36.58 seconds.

The selected arcade frame uses pixel typography, a central relative-speed
readout, and the Atari brick colors. Its illustrated game interiors are fully
covered by the verified replay, scaled with nearest-neighbor interpolation.
The MP4 is 1672×940 at 60 fps; the README preview loops at 640×360.
Built-in image generation updated the selected artwork's numeric labels and
settings text. The exact edit prompt is saved in the policy archive at
`presentation/artwork-generation.json`; gameplay is provided by the verified
replay rather than the generated illustration.
The frame's muted vertical stack below the speedup identifies the throughput workload: one
environment, frame skip 2, frame stack 4, and 84×84 grayscale observations with
area resizing, no last-two-frame max pooling, and a zero mask over the top 17
rows before resizing. Observations use CHW layout. These pixel settings match
the resolved recipe saved with the checkpoint; playback also uses frame skip 2.
Each setting occupies its own line with `=` separators, smaller type, and more
space between lines. The frame has no Benchmark heading or separate replay
frame-skip label.

Playback illustrates relative environment throughput; it is not a screen
recording of execution time. Policy inference, rendering, and encoding are
excluded from the throughput figure. The timing workload and policy both advance
two native frames per step. No claim is made
that the measured ratio describes policy inference or full-wall completion time.

## Full-episode parity failure

The full replay fails cross-provider parity. Its first rendered-frame mismatch
occurs after raw action 5,914; selected information first differs at action
7,164. Native completes the first wall at score 432 with three lives. Stable
Retro terminates after action 7,578 at score 431 with no lives. The cause has
not been diagnosed or fixed in this media task.

The comparison ends at the preceding exact policy decision boundary. The
evidence preserves both full replay records and the failure disclosure, as
well as the passing excerpt check. Every initial and decision-boundary frame
of the separate full native video matches the original GradLab playback.

## Diagnostic timing evidence

The displayed timing evidence comes from the October 2, 2026 TurboBench source
checkout with the new immutable `breakout/firstwall-policy-v1` profile, using
the published macOS arm64 wheels on an Apple M1
Pro, eight logical CPUs, 16 GiB RAM, and CPython 3.14.5. The benchmark used
phase-isolated processes and fresh environments.

**These are busy-host diagnostic measurements, not a validated performance
claim.** The Mac exceeded TurboBench's load threshold, so timing used
`--force-busy`. At the user's request, the artwork has no diagnostic badge.
The README caption, this method document, and the manifest retain the diagnostic
classification and full timing and replay limitations.
The original four-frame benchmark remains unchanged as historical evidence;
its timings are no longer used in the video. The policy-derived benchmark
passes all correctness and contract gates, but its one-lane shape override and
busy-host override prevent an official claim. An earlier new-profile attempt
selected an incorrect ambient reference state and failed correctness; its
timings are excluded. The corrected profile pins the canonical Start digest.

| Lanes | Native median transitions/s | Stable Retro median transitions/s | Paired ratio | Paired 95% CI |
| ---: | ---: | ---: | ---: | :---: |
| 1 | 38,935.6 | 1,097.3 | 35.1304× | [33.2212, 37.4296] |

Each shape used one warmup pair, seven alternating measurement pairs, and three
repetitions per invocation. Timing includes stepping, observation processing,
IPC, information values, terminal detection, and selective resets. The video
uses only the one-lane ratio. It is a seeded matched environment workload;
the recorded policy actions supply the separate exact video replay.

This is an environment throughput measurement rather than the full GradLab
training pipeline. The benchmark uses owned observation buffers and one native
thread for one lane; training uses safe-view observations and six native threads.
Both benchmark providers use the policy's three-action table. The benchmark
excludes policy inference, the policy's context dictionary, task reward shaping,
and its auto-serve rule. GradLab playback retains the saved training contract,
including reset noops and auto-serve; its contract reports `matches_training=true`.

## Verification artifacts

- [Policy-media manifest and output hashes](../media/speed-comparison/media-manifest.json)
- [Policy replay evidence archive](../media/speed-comparison/policy-replay.tar.gz)
- [Policy-derived benchmark report](../media/speed-comparison/policy-benchmark-report.md)
- [Policy-derived benchmark bundle](../media/speed-comparison/policy-benchmark.tar.gz)
- [Original benchmark report](../media/speed-comparison/benchmark-report.md)
- [Original portable benchmark bundle](../media/speed-comparison/benchmark.tar.gz)

The policy archive includes the semantic action streams, captured decision
provenance, full replay hashes, exact excerpt verification, failure disclosure,
provider contract attestations, and a SHA-256 inventory. It excludes model
weights, raw frame payloads, ROMs, save states, and local asset paths. The media
manifest binds each encoded output to the checkpoint, providers, action stream,
diagnostic benchmark, and replay checks.

The historical four-frame benchmark bundle ID is
`753a371000642961c76866c18a5efff1aa632f77c90faf4dea285e4cf084a6e0`.
Its TurboBench source commit was
`5d79063ab8bbfa32e1a85d5a385f041ef842bd44`.
Verify the benchmark after extraction, from this repository's root:

```bash
mkdir -p /tmp/breakout-speed-evidence
tar -xzf media/speed-comparison/benchmark.tar.gz -C /tmp/breakout-speed-evidence
uv run --directory ../turbobench --frozen turbobench verify /tmp/breakout-speed-evidence/benchmark
```

To verify the policy evidence inventory, extract it and run `shasum`:

```bash
tar -xzf media/speed-comparison/policy-replay.tar.gz -C /tmp/breakout-speed-evidence
(cd /tmp/breakout-speed-evidence/policy-replay && shasum -a 256 -c SHA256SUMS)
```

The new benchmark requires the TurboBench checkout containing
`breakout/firstwall-policy-v1`; released `2.0.7` alone does not include this
profile. Its exact profile document is included in both evidence archives.

```bash
tar -xzf media/speed-comparison/policy-benchmark.tar.gz -C /tmp/breakout-speed-evidence
uv run --directory ../turbobench --frozen turbobench verify /tmp/breakout-speed-evidence/policy-benchmark
```

## Refreshing the comparison

An official comparison requires fresh matched timing on an idle host and exact
replay of the selected policy trajectory. Diagnose the full-episode mismatch
before using completed-wall gameplay as a matched comparison. Keep GradLab
capture and TurboBench comparison logic in their owning repositories.

For future policy playback and comparison media, use the environment details
saved with the selected policy as the authority. Read its resolved recipe and
training contract, rather than defaults in an environment or benchmark profile.
Require matching frame skip, frame stack, crop/mask, resizing, grayscale, max
pooling, sticky actions, action table, reset behavior, and policy inputs for
playback. Verify the playback contract against training before rendering.
Derive benchmark pixel settings from that same recipe and fail on a mismatch.
TurboBench's `require_policy_frame_skip` guard runs before benchmarking or
rendering this policy. It rejects a mismatch between the saved training recipe,
captured training/playback contract, policy decision cadence, benchmark, or
render action-stream metadata. It also checks that the expanded raw actions
repeat each recorded policy decision exactly the training number of frames
and end at a complete decision boundary. Raw-frame rendering itself advances
one frame per expanded action; this preserves the policy's two-frame cadence.
The selected artwork's frame-skip value must match the same validated value.
Document deliberate workload or timing-boundary differences, including lane
count, thread count, buffer ownership, and excluded wrappers; never describe
an environment-only benchmark as the full policy pipeline. If required policy
metadata is missing, obtain it from the training run before proceeding.
