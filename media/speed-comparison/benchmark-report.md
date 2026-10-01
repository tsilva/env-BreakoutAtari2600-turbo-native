# Turbobench: breakout/start-v1

- Validity passed: `false`
- Claim status: `diagnostic`
- Shape-1 outcome: `left_faster`
- Promo eligible: `false`
- Execution protocol: `turbobench.phase-isolated-execution/v1`
- Left: `env-breakoutatari2600-turbo-native==0.5.13`
- Right: `stable-retro==1.0.1`

## Shape-local results

| Envs | Left median SPS | Right median SPS | Left/right ratio | 95% paired CI | Outcome |
| ---: | ---: | ---: | ---: | :---: | :--- |
| 1 | 34,436.6 | 773.5 | 45.0552× | [36.4204, 45.8494] | left_faster |
| 16 | 130,341.4 | 2,941.8 | 42.0406× | [41.6233, 52.0270] | left_faster |
| 32 | 104,350.5 | 2,958.7 | 34.4495× | [28.5921, 38.0576] | left_faster |

No SPS values are aggregated across shapes. Shape 1 is the promo basis.

## Validity gates

- **PASS** — compatible profile pair: env-breakoutatari2600-turbo-native versus stable-retro
- **PASS** — canonical assets: canonical payload and state catalog found
- **PASS** — isolated runtimes: separate content-addressed Python environments
- **PASS** — common Python minor: 3.14
- **PASS** — common harness lock: gymnasium==1.2.2, numpy==2.4.2
- **PASS** — eligible exact artifacts: no dirty/quarantined/relaxed provider artifacts
- **PASS** — correctness at every shape: 1=pass, 16=pass, 32=pass
- **PASS** — Turbo API validity: left/shape-1=api2:pass, left/shape-16=api2:pass, left/shape-32=api2:pass, right/shape-1=apiNone:pass, right/shape-16=apiNone:pass, right/shape-32=apiNone:pass
- **PASS** — phase-isolated execution protocol: every workload process references its exact successful contract attestation
- **PASS** — official sample design: configured full shapes, warmups, and alternating pairs
- **FAIL** — system load: one-minute load below 4.0; forced=True
- **PASS** — official host platform: Apple-silicon macOS or x86-64 Linux
- **PASS** — offline measurement: network disabled in correctness, timing, and replay subprocesses
- **FAIL** — no diagnostic overrides: force-busy override

## Method

Each official shape uses one unmeasured warmup pair followed by seven alternating AB/BA measured pairs. Every invocation contains three repetitions; invocation medians form paired ratios and a deterministic 20,000-resample bootstrap 95% confidence interval.

Contract validation, correctness traces, warmups, timed measurements, and promotional replay use phase-isolated provider processes and fresh environment instances. Each workload evidence record references the successful attestation for its exact execution configuration.

Timed SPS includes preprocessing, IPC, infos, terminal detection, and selective resets. It excludes construction, initial reset, action generation, warmup, correctness replay, rendering, and encoding.
