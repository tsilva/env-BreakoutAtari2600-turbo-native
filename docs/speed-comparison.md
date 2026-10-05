# Trained-policy speed comparison

This comparison, started October 4, 2026, uses the published **TurboBench 2.0.11** wheel,
native **0.5.15**, and original **Stable Retro 1.0.1**. The benchmark ran on
`private-host-redacted`; exact replay and media generation ran separately on an
Apple M1 Pro. The full verified proof is attached to the
[benchmark release](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/benchmark-v0.5.15-20261004-tb2.0.11). The library's [v0.5.15 release](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/v0.5.15)
and its canonical parity receipt remain separate evidence.

The README's [animation](../demo.webp) and [MP4](../demo.mp4) are exports from
the refreshed style v4 showcase proof described below. The
[complete chart](../benchmark.svg) now uses simplified publication labels;
benchmark measurements and the archived chart are unchanged.
[demo-manifest.json](../demo-manifest.json) records their digests and the archive
reference; it is a publication pointer, not a standalone TurboBench proof.

## Results and scaling

The benchmark host is an AMD Ryzen 5 7600X with six physical cores, twelve
logical CPUs, and approximately 61 GiB RAM, running x86-64 Linux and CPython
3.14.6. Both provider runtimes use Gymnasium 1.2.2 and NumPy 2.4.2. Every measured
count passed phase-isolated contract validation and exact correctness checks
before timing. The load gate passed without overrides; the result is official
for this frozen workload and host.

| n_envs | Stable Retro median SPS | Native median SPS | Native/upstream paired speedup | Paired 95% CI |
| ---: | ---: | ---: | ---: | :---: |
| 1 | 192.6 | 69,797.5 | 362.30× | [358.47, 366.10] |
| 2 | 377.4 | 124,814.6 | 331.04× | [316.39, 332.47] |
| 4 | 732.5 | 218,855.1 | 298.26× | [290.64, 305.13] |
| 8 | 1,032.3 | 258,955.4 | 251.21× | [249.10, 270.88] |
| 16 | 1,247.5 | 276,118.0 | 221.98× | [219.31, 224.02] |
| 32 | 1,342.4 | 353,326.8 | 263.21× | [261.24, 265.77] |
| 64 | 1,389.7 | 418,587.7 | 300.97× | [298.86, 302.43] |
| 128 | 1,408.1 | 361,149.5 | 256.48× | [254.61, 256.76] |
| 256 | 1,423.2 | 173,169.7 | 121.52× | [120.64, 122.43] |

SPS counts environment transitions, including every lane, rather than raw
Atari frames. Each count uses one unmeasured warmup pair and seven alternating
AB/BA pairs with three repetitions per invocation. Invocation medians form the
paired ratios; the 95% interval uses a deterministic 20,000-resample paired
bootstrap. Ratios and intervals above invert TurboBench's left/right statistic
so that native/upstream is shown consistently. Counts are never aggregated.

The controller was interrupted after completing counts 1, 2, 4, and 8 and the
first upstream invocation at 16. The same frozen 2.0.11 request resumed using
its validated completed invocations; contract and correctness checks ran again
before timing continued. Measurements from the earlier interrupted 2.0.10
request are excluded.

An additional SSH transport interruption occurred while measuring count 256.
Completed invocations remained in the content-addressed job; the final proof
contains only validated measurements bound to the same frozen request.

The predeclared adaptive rule doubles `n_envs` from one. A provider qualifies
after two successive counts gain less than 3% against its own best previous
median, or immediately after a decline of at least 5%. Both must qualify before
stopping; every measured confirming or slower count remains in the complete chart.
The proof's `benchmark/verification/scaling.json` records the complete decisions.
The sweep stopped at **256 environments**: Stable Retro: plateau, +1.1% versus its earlier best median; native: downgrade, -58.6% versus its earlier best median.
This throughput heuristic does not supply a statistical interval for the peak's
location. The cap is 1,024 environments; reaching it alone would be diagnostic.

## Readable README chart

The [README chart](../benchmark-readme.svg) uses an 800×420 canvas, side-by-side
vertical bars on one shared zero-based linear scale, whole-number SPS labels,
and paired speedups. The top-right legend uses 14px text; SPS and speedup
values use 13px text, and environment counts use 14px text.
Both published chart views omit inline confidence intervals
and bottom explanatory labels; exact medians and intervals remain in the table
above and immutable proof. Display rounding does not change bar heights. The
README shows the measured prefix through the first maximum native median
throughput: **1, 2, 4, 8, 16, 32, 64**.
The cutoff uses native throughput, not the native/upstream speedup ratio.
The native decline at **128 and 256** is omitted only from this presentation;
all nine counts remain in the results table above, [complete chart](../benchmark.svg),
and immutable benchmark proof. This display choice does not change the
predeclared stopping rule or claim uncertainty about the peak location.

This chart is a derived publication export, separate from the immutable
showcase assets. [benchmark-readme.json](../benchmark-readme.json) binds the
benchmark proof ID, original result digest, renderer file digest, selected
and omitted counts, and SVG digest. [demo-manifest.json](../demo-manifest.json)
pins renderer source revision [`9827b1f`](https://github.com/tsilva/turbobench/commit/9827b1f8d9fe3dc7a736ead802f67e7396124709).
The [complete chart publication record](../benchmark.json) binds all nine
counts and the same verified result. The archive retains its original chart;
the repo's complete publication view has simplified labels.
These chart refinements do not alter the measurements or video timeline.

After downloading and extracting the refreshed proof using the instructions
below, reproduce the README export with that exact renderer source:

```bash
curl -fL https://github.com/tsilva/turbobench/archive/9827b1f8d9fe3dc7a736ead802f67e7396124709.tar.gz -o readme-renderer.tar.gz
tar -xzf readme-renderer.tar.gz
uv run --frozen --python 3.14 --project turbobench-9827b1f8d9fe3dc7a736ead802f67e7396124709 python -m turbobench.readme_chart \
  "$PWD/proof/benchmark" "$PWD/benchmark-readme.svg"
uv run --frozen --python 3.14 --project turbobench-9827b1f8d9fe3dc7a736ead802f67e7396124709 python -m turbobench.readme_chart \
  "$PWD/proof/benchmark" "$PWD/benchmark.svg" --full
```

Compare the generated SVG and JSON digests with the repository's publication
records. The command verifies the benchmark proof before exporting; it needs
no ROM, state, inference, or new measurements. Published TurboBench 2.0.11 still
verifies the unchanged benchmark child; this README renderer is pinned separately.

## Policy, controls, and timing boundary

The selected FirstWall PPO checkpoint was trained for 191,561,728 steps:

- SHA-256: `dcfd8a41bcc7426ac0ef2f108d07a20f2ffb2c0c22745e6690c6065c01d5935a`
- Training run in MLflow (run `e10b9f9dfec247b881d2eac3979dda37`)
- Policy proof: `d1656f3e45f41694846ba3921b88312e35b326962bf233f80afb5fff55d5f0fe`
- Complete saved recipe, checkpoint, effective actions, and selection disclosure
  are included under `policy/` in the archive.

The benchmark does **not** execute inference or choose new random actions.
It replays the locked effective policy decisions, including captured serve
overrides, after reset seed 1,000,000 and the captured 21 raw no-op prefix.
Each invocation measures all 2,946 selected decisions. Every lane and repetition
starts from the same captured seed and follows the same controls; correlated
lanes are a declared workload choice, not an estimate of policy success.

The saved training contract uses frame skip 2, stack 4, CHW 84×84 grayscale,
area resizing, a zero mask over the top 17 raw rows, no max pooling, no sticky
actions, and no fire reset. Benchmark buffers are owned (`obs_copy=copy`) and
threads equal `n_envs`, differing from training's safe-view buffers and six
native threads. The exact ordered training action table is preserved.

Timing includes environment stepping, observation preprocessing, IPC, infos,
terminal detection, and required selective resets. It excludes construction,
initial seeded reset, warmup, policy inference, task/context/reward wrappers,
correctness hashing, recording, chart generation, rendering, and encoding.
Correctness and timing run in separate processes and fresh instances. The
complete decision-level trace is checked at every measured count; the raw
policy capture is replayed and compared on both hosts before rendering.

The imported policy contract contains a historical note describing seeded
benchmark controls. The generated report identifies the current policy controls.
For this run, `comparison-request/v3`, `paired-policy/v2`, and every
`result.json` action record bind **captured-policy/v1** controls for both
correctness and measurement; those executable commitments determine the actual
timing workload.

## Excerpt and parity limits

The selected excerpt contains 2,946 of 4,139 captured policy decisions: 5,913
effective raw actions and 5,914 frames including the initial frame. It ends at
score 429, four lives, and three bricks remaining. Exact observations, rendered
frames, rewards, lifecycle, selected infos, and declared snapshot continuation
checks pass. Linux benchmark and macOS render replay commitments match.

The historical full native 0.5.13 attempt cleared the first wall, but its
cross-provider replay diverged after raw action 5,914; selected info first
differed at action 7,164, and Stable Retro later terminated. That historical
failure remains a limitation of the imported selection. This 0.5.15 run checks
the selected excerpt and does not rerun or certify that full attempt. Neither
this excerpt nor one successful native episode establishes completed-wall
parity, a success rate, or equivalence with the Arcade Learning Environment.

## Refreshed frame and media proof

The README media was re-rendered on October 5, 2026 with **Same Actions**,
small gaps on both sides of the title, the **speedup** label directly below
the multiplier, and a compact divider/settings block below it. Each **SPS**
unit sits immediately beside its number regardless of digit count.
The MP4 and animated WebP retain 1672×940 resolution, 26.65-second duration,
the original playback ratio, and the same effective action trajectory.
The WebP remains lossless, nominally 20 fps, and loops indefinitely; the
silent H.264 MP4 remains 60 fps.

The [refreshed showcase proof](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/showcase-v0.5.15-20261005-style4) uses `comparison-style/v4` and
TurboBench renderer source revision [`cfc7a19`](https://github.com/tsilva/turbobench/commit/cfc7a19dc8d243c725f4b604658bc640cb587124).
Its benchmark and policy child proofs are unchanged, and its archived chart is
byte-identical to the original. Fresh untimed replay passes the original
cross-host commitments. No benchmark was rerun and no measurements were edited.
The previous [style v3 proof](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/showcase-v0.5.15-20261005-style3) and original
[benchmark release](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/benchmark-v0.5.15-20261004-tb2.0.11)
retain their immutable media and verification instructions.

Download `breakout-policy-showcase-env0.5.15-style4.tar.gz` and `SHA256SUMS` from the refreshed showcase release
into a fresh directory. The **published 2.0.11 verifier checks the benchmark
child**; the **pinned source revision checks the complete refreshed media proof**.
Style v4 is not included in the published 2.0.11 wheel.

```bash
shasum -a 256 -c SHA256SUMS
tar -xzf breakout-policy-showcase-env0.5.15-style4.tar.gz
uvx --python 3.14 --exclude-newer-package turbobench-cli=2026-10-05 --with numpy==2.5.1 --with pillow==12.3.0 --with packaging==26.2 \
  --from turbobench-cli==2.0.11 turbobench verify proof/benchmark
curl -fL https://github.com/tsilva/turbobench/archive/cfc7a19dc8d243c725f4b604658bc640cb587124.tar.gz -o renderer.tar.gz
tar -xzf renderer.tar.gz
uv run --frozen --python 3.14 --project turbobench-cfc7a19dc8d243c725f4b604658bc640cb587124 turbobench verify "$PWD/proof"
```

Both verification steps require FFprobe but no ROM, save state, inference, or
remeasurement. The source verifier uses the committed dependency lock.

- Refreshed archive SHA-256: `dffbf3e79988ad12cfaa77411e1d810e76cc5571626f35e9c6dfb11c405e8ff8`
- Refreshed showcase proof: `a8fc9c6f0172da3d2b1d86c9095e1e770983316f72a6c0757145dc52af1155c1`
- Benchmark proof: `7a7df46f83e4be2a26fe7dbcc212fb2305860a317af1d8fc92206c03ac2f8214`
- Policy proof: `d1656f3e45f41694846ba3921b88312e35b326962bf233f80afb5fff55d5f0fe`
- Render harness SHA-256: `b77013e734fb7540fea2b5fb18eac3e810f68e94803bb8ebb8529eb35ea0e19b`

## Original proof: download and verify

With `uv` and FFprobe installed, download `breakout-policy-showcase-tb2.0.11-env0.5.15.tar.gz` and `SHA256SUMS` from the
[benchmark release](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/benchmark-v0.5.15-20261004-tb2.0.11) into a fresh directory, then run:

```bash
shasum -a 256 -c SHA256SUMS
tar -xzf breakout-policy-showcase-tb2.0.11-env0.5.15.tar.gz
uvx --python 3.14 --exclude-newer-package turbobench-cli=2026-10-05 --with numpy==2.5.1 --with pillow==12.3.0 --with packaging==26.2 \
  --from turbobench-cli==2.0.11 turbobench verify proof
```

Verification uses the exact [published TurboBench 2.0.11](https://pypi.org/project/turbobench-cli/2.0.11/)
verifier. It requires no ROM, save state, inference, or remeasurement. The
three controller dependencies above match the published workflow lock. The
package-specific cutoff admits the selected October 4 TurboBench release even
when a local seven-day quarantine is configured. The
archive includes bound raw measurements, runtime locks, schemas, checkpoint,
recipe, actions, replay digests, media, and the untouched generated report.
It excludes ROMs, provider save states, raw reference frames, and private asset
paths. Integrity verification establishes internal consistency, not author
authentication or independent reproduction of the timings.

- Archive SHA-256: `0b3cf31ee3b97e3f0ef633249087ad97ff4f8658a99d8a2965b42892b3dcb9b9`
- Showcase proof: `b82ebbeefbef6c4319b314cda146b1c7727fa4e4c4823c041cd0f45783a5735d`
- Benchmark proof: `7a7df46f83e4be2a26fe7dbcc212fb2305860a317af1d8fc92206c03ac2f8214`
- Harness SHA-256: `85da540ed868f812717bea83b885d13f08889d6b2b5d6d93c27b10964da9f2b8`
- TurboBench release source: `a9683e3d07fd536f87bc09209fa29b20dd5eaa0d`
- Published verifier wheel SHA-256: `e7ae9d3104b9016159e4739fc2ab7e5065da67cfaf0f3d585829e2ac86a5b060`

To repeat the same workload with lawful canonical assets on both hosts and the
extracted policy package, configure an idle SSH benchmark host and run from
the separate rendering machine:

```bash
uvx --python 3.14 --exclude-newer-package turbobench-cli=2026-10-05 --with numpy==2.5.1 --with pillow==12.3.0 --with packaging==26.2 \
  --from turbobench-cli==2.0.11 turbobench compare \
  --policy-benchmark --showcase --policy "$PWD/proof/policy" \
  --benchmark-host private-host-redacted \
  --right env-breakoutatari2600-turbo-native@0.5.15 \
  --output breakout-policy-rerun
```

See TurboBench's [two-host workflow](https://github.com/tsilva/turbobench/blob/turbobench-cli-v2.0.11/docs/comparison-workflow.md)
for asset setup, rendering tools, and host requirements. GradLab owns policy
training and inference capture; TurboBench owns comparison logic and media.
