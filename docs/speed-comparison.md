# Trained-policy speed comparison

The README's [animated WebP preview](../demo.webp), [MP4](../demo.mp4),
and [media manifest](../demo-manifest.json) compare native `0.5.13` with
original Stable Retro `1.0.1`. GradLab owns policy playback and inference;
TurboBench owns provider replay, benchmarking, and comparison rendering.

## Policy and replay

The comparison uses GradLab's final FirstWall PPO checkpoint, trained for
191,561,728 steps:

- Run: `gradlab-2ab417e09bfa4a0c1946070089b23fe0`
- Checkpoint: `checkpoint-191561728-dcfd8a41bcc7426a`
- SHA-256: `dcfd8a41bcc7426ac0ef2f108d07a20f2ffb2c0c22745e6690c6065c01d5935a`
- [Training run in MLflow](https://mlflow-beast3.tsilva.eu/#/experiments/6/runs/e10b9f9dfec247b881d2eac3979dda37)

Playback used the saved training contract, stochastic sampling at temperature
1, auto-serve, and seed 1,000,000. The first native attempt cleared 108 bricks
at score 432 with three lives, reaching GradLab `SUCCESS` after 4,139 policy
decisions. A single playback does not establish a success rate.

Both providers replay the same effective actions, including auto-serve overrides
and 21 raw reset noops. Each policy decision repeats its action for two frames.
The displayed excerpt matches exactly through 2,946 decisions: 5,913 raw actions
and 5,914 frames including the initial frame. Frames, observations, rewards,
terminal flags, and selected info all match. It ends at score 429, four lives,
and three bricks remaining.

Observations use frame skip 2, frame stack 4, 84×84 grayscale in CHW layout,
area resizing, no max pooling, and a zero mask over the top 17 rows before
resizing. These settings match the checkpoint's saved recipe.

Playback illustrates relative environment throughput and excludes inference,
rendering, and encoding. Both panels share a 4× display acceleration: Stable
Retro plays at 4× and native at 140.5215×, preserving the measured 35.1304× ratio.
This ratio does not measure full-policy or completed-wall execution time.

## Full-episode parity failure

The full replay with native `0.5.13` failed parity: the first rendered-frame
mismatch follows raw action 5,914, and selected info first differs at action
7,164. Native finishes the first wall at score 432 with three lives; Stable
Retro terminates at action 7,578 with score 431 and no lives. The media task
did not diagnose or fix this mismatch.

The excerpt stops at the preceding exact policy decision boundary. The local
evidence retains both full replay records, the failure disclosure, and the
passing excerpt check. The full native video's initial and decision-boundary
frames match the original GradLab playback.

## Diagnostic timing evidence

**These busy-host measurements do not support an official performance claim.**
TurboBench's October 2, 2026 source checkout used `breakout/firstwall-policy-v1`,
published macOS arm64 wheels, phase-isolated processes, and fresh environments
on an Apple M1 Pro with eight logical CPUs, 16 GiB RAM, and CPython 3.14.5.
The profile pins the canonical Start digest and passes correctness and contract
gates; `--force-busy` and a one-lane shape override prevent official status.

| Lanes | Native median transitions/s | Stable Retro median transitions/s | Paired ratio | Paired 95% CI |
| ---: | ---: | ---: | ---: | :---: |
| 1 | 38,935.6 | 1,097.3 | 35.1304× | [33.2212, 37.4296] |

Timing uses one warmup pair, seven alternating measurement pairs, and three
repetitions per invocation. It includes stepping, preprocessing, IPC, info,
terminal detection, and selective resets. This seeded workload is separate
from the recorded policy-action replay used for the video.

The benchmark uses owned observation buffers, one native thread, and the
policy's three-action table. Training uses safe-view observations and six
native threads. Timing excludes inference, the policy context dictionary,
task reward shaping, and auto-serve. GradLab playback retains reset noops and
auto-serve under its verified training contract (`matches_training=true`).

## Evidence and refresh requirements

The public [media manifest](../demo-manifest.json) binds encoded outputs to the
checkpoint, providers, actions, diagnostic timing, and replay checks. Full
playback and replay/benchmark archives remain in ignored
`media/speed-comparison/`; they are absent from checkouts and Python packages.
`policy-replay.tar.gz` contains action streams, decision provenance, replay
hashes, excerpt verification, failure disclosure, provider contracts, and
`SHA256SUMS`. It excludes weights, raw frames, ROMs, save states, and asset paths.
Verify extracted replay files against `SHA256SUMS` and benchmark bundles with
`turbobench verify`. The policy profile requires the source checkout containing
`breakout/firstwall-policy-v1`; TurboBench `2.0.7` lacks it. Both policy evidence
archives include the exact profile.

An official comparison requires matched timing on an idle host and exact replay
of the selected trajectory. Resolve the full-episode mismatch before presenting
completed-wall gameplay as a matched comparison.

Use the policy's saved recipe and training contract for playback and benchmark
settings: frame skip/stack, crop/mask, resizing, grayscale, max pooling, sticky
actions, action table, resets, and policy inputs. Obtain missing metadata from
the training run. TurboBench's `require_policy_frame_skip` guard must verify
training/playback contracts, decision cadence, benchmark and render metadata,
repeated raw actions, and complete decision boundaries before timing or
rendering. Artwork labels must agree. Document differences in lanes, threads,
buffer ownership, and excluded wrappers; keep capture and comparison logic in
GradLab and TurboBench.
