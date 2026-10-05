# Latest benchmark

Started October 4, 2026 · **Native 0.5.15 vs Stable Retro 1.0.1** · **TurboBench 2.0.11**

Measured on **AMD Ryzen 5 7600X**, 6 cores / 12 threads,
61 GiB RAM, x86-64 Linux, Python 3.14.6. Replay and media generation ran on a
separate Apple M1 Pro. Contract, correctness, and load gates passed without overrides.

## Results and scaling

**362.30× speedup at one environment** (paired 95% CI: **358.47–366.10×**).
Peak native throughput: **418,588 steps/s at 64 environments**.

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

SPS counts environment transitions across all lanes, not raw Atari frames.
The [README chart](benchmark-readme.svg) stops at the measured native peak;
[the complete chart](benchmark.svg) and table retain 128 and 256.
The sweep stopped at 256 after upstream plateaued and native throughput declined;
the stopping rule does not estimate uncertainty in the peak's location.

## Method and policy

- **Controls:** captured FirstWall PPO actions (run `e10b9f9dfec247b881d2eac3979dda37`), including serve overrides; no random actions or timed inference. Each lane replays the same 2,946 decisions from seed 1,000,000 after 21 raw noops. The checkpoint, recipe, and actions are locked in the proof's `policy/` directory.
- **Configuration:** frame skip 2, stack 4, CHW 84×84 grayscale, area resize, top-17-row zero mask, no max pooling, sticky actions, or fire reset. Training's ordered action table is preserved. Benchmark uses `obs_copy=copy` and `num_threads=n_envs`; training used safe-view buffers and six threads.
- **Timing:** includes stepping, preprocessing, IPC, infos, terminal detection, and selective resets. Excludes construction, initial reset, warmup, inference, task/context/reward wrappers, correctness checks, recording, and rendering. Correctness and timing use separate processes and fresh instances.
- **Sampling:** one warmup pair, seven alternating AB/BA pairs, three repetitions per invocation. Speedups use paired invocation medians; 95% CIs use a deterministic 20,000-resample paired bootstrap. Counts are analyzed separately.
- **Scaling:** double `n_envs` until each provider qualifies through a plateau (two successive gains below 3% against its own previous best) or downgrade (at least 5% below its previous best). The cap is 1,024; reaching it alone is diagnostic. Decisions are recorded in `benchmark/verification/scaling.json`.

## Parity and media limits

The checked excerpt covers **2,946 of 4,139 captured decisions**, ending at
**score 429, four lives, three bricks remaining**. Exact observations, rendered
frames, rewards, lifecycle, selected infos, and snapshot continuation checks
pass; Linux and macOS replay commitments match.

This establishes excerpt parity, not full-capture or completed-wall parity,
a policy success rate, or Arcade Learning Environment equivalence. The imported
full-capture disclosure records a mismatch at raw frame 5,914.

The [animation](demo.webp) and [MP4](demo.mp4) use the measured ratio and common
**4× time compression**, not wall-clock playback. Their latest export uses
`comparison-style/v5`; the benchmark and policy proofs are unchanged.

## Proof and verification

Download the [latest proof archive and SHA256SUMS](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/showcase-v0.5.15-20261005-style5).
[demo-manifest.json](demo-manifest.json) records archive, provider, policy, and
media identities and hashes. [README chart provenance](benchmark-readme.json)
and [complete chart provenance](benchmark.json) bind the derived charts; their
renderer is pinned to [9b64ddd](https://github.com/tsilva/turbobench/commit/9b64dddefdaca874a65a5dbd4e4bb140bde83025).

Published **TurboBench 2.0.11** verifies the benchmark child. Pinned source
[10fc93d](https://github.com/tsilva/turbobench/commit/10fc93d737671765269e07321de37f76345590b5)
verifies the complete `comparison-style/v5` proof. Both need FFprobe; verification needs no ROM.

```bash
shasum -a 256 -c SHA256SUMS
tar -xzf breakout-policy-showcase-env0.5.15-style5.tar.gz
uvx --python 3.14 --exclude-newer-package turbobench-cli=2026-10-05 --with numpy==2.5.1 --with pillow==12.3.0 --with packaging==26.2 \
  --from turbobench-cli==2.0.11 turbobench verify proof/benchmark
curl -fL https://github.com/tsilva/turbobench/archive/10fc93d737671765269e07321de37f76345590b5.tar.gz -o renderer.tar.gz
tar -xzf renderer.tar.gz
uv run --frozen --python 3.14 --project turbobench-10fc93d737671765269e07321de37f76345590b5 turbobench verify "$PWD/proof"
```

The archive excludes ROMs, save states, raw reference frames, and private paths.
Verification checks internal consistency, not author authentication or independent timing reproduction.
For reruns and chart export commands, see the pinned [benchmark workflow](https://github.com/tsilva/turbobench/blob/turbobench-cli-v2.0.11/docs/comparison-workflow.md)
and [chart renderer](https://github.com/tsilva/turbobench/blob/9b64dddefdaca874a65a5dbd4e4bb140bde83025/docs/comparison-workflow.md).
[Library release parity](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/v0.5.15) is separate evidence.

## Earlier proof references

- [Original benchmark/showcase](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/benchmark-v0.5.15-20261004-tb2.0.11)
- [Style v3 export](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/showcase-v0.5.15-20261005-style3)
- [Style v4 export](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/releases/tag/showcase-v0.5.15-20261005-style4)
