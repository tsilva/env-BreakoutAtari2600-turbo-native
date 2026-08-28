# Specification compliance

This matrix maps every project requirement in [`SPECS.md`](../SPECS.md) to
maintained evidence. The quoted requirements are intentionally literal and
ordered; `tests/test_spec_compliance.py` fails when the specification and this
matrix drift. Every Python test selector includes its repository path and is
directly executable with `.venv/bin/python -m pytest <selector>`. Rust node IDs
are directly executable with `cargo test --locked --lib <node-id>`.

The regular verification set is `.venv/bin/python -m pytest -m
"not stable_retro"`, `cargo test --locked --lib`, `.venv/bin/python -m ruff
check .`, `cargo fmt --check`, `cargo clippy --locked --all-targets -- -D
warnings`, and `cargo check --locked --release`. The private-ROM acceptance set
is the fixed `make test-semantic-oracle` command documented in
[`release-validation.md`](release-validation.md). It is the sole certifying
Stable Retro Turbo gate.

## Product boundary

<!-- SPECS:1 -->
> Use `env-BreakoutAtari2600-turbo-native` as the project and GitHub repository name, `env-breakoutatari2600-turbo-native` as the Python distribution name, and `env_breakoutatari2600_turbo_native` as the public Python import package; current project-owned identities must not use any former project, distribution, import, or command identifier.

Evidence: `tests/test_spec_compliance.py::test_current_project_surfaces_do_not_restore_former_identifiers`, `tests/test_community.py::test_package_metadata_exposes_public_project_identity`, and `tests/test_cli.py` exercise the maintained names and command.

<!-- SPECS:2 -->
> Normal environment use must require no Atari ROM, emulator, original Stable Retro, or Stable Retro Turbo installation.

Evidence: `tests/test_oracle_configuration.py::test_oracle_dependencies_stay_outside_the_distributed_package`, the clean-wheel smoke in `tests/test_release_build.py::test_built_wheel_smoke_exercises_exact_live_snapshot_replay`, and the regular test suite run without `RETRO_DATA_PATH` exercise the standalone runtime.

<!-- SPECS:3 -->
> The project must distribute no Atari ROM, cartridge dump, provider save state, recorded reference frame, or extracted game asset; oracle validation may use a separately and lawfully obtained ROM.

Evidence: `.github/workflows/oracle-evidence.yml` constructs lawful ROM input only in runner-temporary storage; `tests/test_oracle_release_gate.py::test_receipt_generation_fails_without_lawful_rom` proves the external-input boundary. Non-code review: inspect file lists from `.venv/bin/python .codex/skills/build-release/scripts/release_build.py build-platform --platform macos-arm64` and `.venv/bin/python .codex/skills/build-release/scripts/release_build.py build-sdist`; legal and contribution exclusions are in `THIRD_PARTY_NOTICES.md` and `CONTRIBUTING.md`.

<!-- SPECS:4 -->
> Training implementations must remain outside this repository.

Evidence: `tests/test_community.py::test_readme_delegates_training_to_pinned_gradlab_recipes` rejects a project training command. Non-code review: `git ls-files` contains environment, player, benchmark, validation, and release code but no training implementation.

<!-- SPECS:5 -->
> Stable-Baselines3 and interactive-player dependencies must remain optional rather than core dependencies.

Evidence: `tests/test_release_build.py::test_core_package_keeps_play_dependencies_optional` checks core metadata and optional player isolation; `tests/test_sb3_adapter.py` imports the adapter with a test double, while `docs/environment.md` requires users to install Stable-Baselines3 separately.

<!-- SPECS:6 -->
> Supported binary platforms must be limited to Apple-silicon macOS and x86-64 Linux.

Evidence: `tests/test_community.py::test_community_files_and_platform_contract_are_present`, `tests/test_release_build.py::test_wheel_audit_accepts_only_supported_platform_metadata`, and the two-entry package matrix in `.github/workflows/ci.yml` enforce the supported binary platforms and floors.

## Vector environment

<!-- SPECS:7 -->
> The vector environment must step every lane from one batched action input and return observations and transition results that conform to its declared Gymnasium spaces.

Evidence: `tests/test_env.py::test_registered_vector_entry_point_matches_declared_spaces`, `tests/test_env.py::test_generic_gymnasium_factory_runs_native_vector_env`, and `tests/test_deterministic_trace.py::test_public_trace_is_invariant_across_supported_execution_shapes` exercise batched public transitions.

<!-- SPECS:8 -->
> Within the same package version, a lane’s trajectory must be bit-identical across supported binary platforms, batch sizes, neighboring-lane behavior, execution orders, and thread counts when its configuration, aligned state, and actions match.

Evidence: `tests/test_deterministic_trace.py::test_public_trace_is_invariant_across_supported_execution_shapes` covers batch, neighbor, order, and thread invariance; `.github/workflows/ci.yml` generates and compares fresh traces on `macos-arm64` and `linux-x86_64` through `scripts/deterministic_trace.py compare`.

<!-- SPECS:9 -->
> The core vector environment must never automatically reset a terminal lane, must reject attempts to step it before reset, and must allow callers to reset selected lanes while leaving unselected lanes byte-exact.

Evidence: `tests/test_env.py::test_terminal_lane_requires_explicit_reset_then_can_continue` and `tests/test_env.py::test_masked_reset_preserves_unselected_lane_exactly` exercise the public core vector environment.

<!-- SPECS:10 -->
> Explicit adapters may automatically reset completed lanes only while preserving terminal observations and leaving other lanes unchanged.

Evidence: `tests/test_sb3_adapter.py::test_adapter_preserves_terminal_observation_and_resets_only_done_lane` proves the explicit SB3 adapter translation.

<!-- SPECS:11 -->
> Serialized snapshots must support exact continuation within the same package version and compatible environment configuration; their format need not be compatible across versions.

Evidence: `tests/test_snapshots.py::test_serialized_and_live_snapshots_replay_the_complete_observable_trace`, `tests/test_env.py::test_snapshot_replay_is_byte_exact`, and the built-wheel snapshot smoke cover exact continuation; `docs/environment.md` states the version/configuration boundary.

<!-- SPECS:12 -->
> Live snapshot handles must remain valid only within their originating environment and its lifecycle.

Evidence: `tests/test_env.py::test_live_snapshot_lifecycle_owner_and_selector_validation_are_atomic` rejects cross-environment and post-close use, and `tests/test_env.py::test_live_snapshots_support_masked_capture_cross_lane_fanout_and_replay` covers valid reuse.

<!-- SPECS:13 -->
> Callers must be able to evaluate action branches from snapshots without mutating the source environment or snapshot.

Evidence: `tests/test_snapshots.py::test_branch_results_are_exactly_the_same_as_real_environment_steps` and `tests/test_env.py::test_branches_cover_all_actions_without_mutating_source` cover public branch results and source immutability.

<!-- SPECS:14 -->
> Native actions must be `0` noop, `1` FIRE, `2` right, and `3` left.

Evidence: `tests/test_action_tables.py::test_simple_preset_exposes_exact_discrete_contract` and `tests/test_env.py::test_stable_retro_button_rows_match_native_actions` assert the four exact mappings.

<!-- SPECS:15 -->
> Action tables must accept the game-owned `simple` table and exact caller-supplied subsets or reorderings of reproducible native actions.

Evidence: `tests/test_action_tables.py::test_packaged_metadata_is_available_and_defines_simple`, `tests/test_action_tables.py::test_inline_subset_and_reordering_map_to_native_commands`, and `tests/test_action_tables.py::test_unreproducible_button_combination_is_rejected` cover the public action table contract.

<!-- SPECS:16 -->
> Stable-compatible filtered actions must retain the eight-button transport, accept only exact noop, FIRE, right, and left rows, disclose those valid rows, and reject every unsupported button or combination without normalization.

Evidence: `tests/test_action_tables.py::test_filtered_invalid_batches_are_rejected_atomically`, `tests/test_action_tables.py::test_filtered_capability_discloses_exact_supported_rows`, and `tests/test_env.py::test_stable_retro_button_rows_match_native_actions` cover validation, atomicity, disclosure, and valid-row equivalence.

<!-- SPECS:17 -->
> The default policy observation per lane must be a grayscale `uint8` CHW stack of four 84×84 frames produced using four native frames per environment step.

Evidence: `tests/test_env.py::test_contract_is_chw_manual_and_no_maxpool`, `tests/test_env.py::test_v2_shared_defaults_resolve_simple_chw_stack`, and `tests/test_env.py::test_frame_skip_matches_repeated_native_physics` verify dtype, shape, stack, and native-console-frame count.

<!-- SPECS:18 -->
> Policy observations and rendered frames must derive independently from the same native 160×210 indexed frame.

Evidence: `tests/test_spec_compliance.py::test_policy_and_render_paths_share_the_native_indexed_pixel_source` guards the source relationship: both Rust `render_indexed` and `policy_gray_pixel` call the same `indexed_pixel` native indexed frame source. `tests/test_env.py::test_incremental_observations_match_forced_full_rebuild`, `tests/test_env.py::test_render_matches_atari_2600_geometry_and_palette`, and the live Stable Retro Turbo suite then cover the independent public outputs.

<!-- SPECS:19 -->
> Rendering must be opt-in, must never advance or mutate game state, must support selecting an individual lane, and must produce the canonical 160×210 Stella RGB rendered frame.

Evidence: `tests/test_env.py::test_rendering_is_disabled_by_default`, `tests/test_env.py::test_render_lane_selects_any_lane_without_mutating_state`, and `tests/test_env.py::test_render_matches_atari_2600_geometry_and_palette` cover the complete rendering contract.

<!-- SPECS:20 -->
> The interactive player must support a configurable display-rate limit and visible uncapped play.

Evidence: `tests/test_play.py::test_play_parser_defaults_and_layout_selection` checks the default and a caller-supplied `--fps`; `tests/test_play.py::test_uncapped_mode_skips_the_frame_limiter` checks the configured capped rate and absence of a limiter in uncapped mode; `tests/test_play.py::test_uncapped_play_remains_visible` runs one uncapped display iteration and asserts its blit, flip, and visible `uncapped` caption.

## Canonical compatibility

<!-- SPECS:21 -->
> Within the documented reproducible subset, callers must be able to replace Stable Retro Turbo with `env-BreakoutAtari2600-turbo-native` for `Breakout-Atari2600-v0` without changing game, state, observation, action, reward, reset, termination, truncation, or shared-information semantics; unsupported provider options must fail immediately.

Evidence: `tests/test_env.py::test_breakout_contract_uses_the_canonical_turbo_provider_surface`, the unsupported-option cases in `tests/test_env.py`, and `tests/test_stable_retro_turbo_oracle.py::test_representative_canonical_trajectories_match_pinned_turbo_provider` cover the public replacement seam.

<!-- SPECS:22 -->
> The pinned Stable Retro Turbo release must be the sole semantic oracle and compatibility target for canonical `Start` behavior.

Evidence: `tests/test_oracle_configuration.py::test_operational_pin_selects_stable_retro_turbo_vector_provider`, `tests/test_oracle_configuration.py::test_make_exposes_one_certifying_turbo_oracle_command`, and `tests/test_spec_compliance.py::test_current_public_contract_never_demotes_the_turbo_oracle` enforce one pin, one gate, and current authority language.

The drift guard inspects Git modes and blobs for every tracked current contract, code, workflow, lock, and release-skill file. It rejects symlinks and invalid UTF-8 text candidates, skips only NUL-marked binary blobs, and subjects its own adversarial test module to the same scan. Phrase-local rules allow only negation that governs the prohibited claim, tightly described upstream/legal provenance, and actual versioned changelog/benchmark history.

<!-- SPECS:23 -->
> After aligning the starting state or reset outcome, every externally observable canonical `Start` trajectory detail must match the oracle under equivalent configuration and actions, including rendered frames, policy observations, rewards, score, lives, termination, truncation, and shared information values.

Evidence: `tests/test_stable_retro_turbo_oracle.py::test_representative_canonical_trajectories_match_pinned_turbo_provider` runs the live suite; `tests/test_oracle_configuration.py::test_live_suite_exercises_one_lane_and_multiple_lanes` guards its complete one-lane and multi-lane observable workloads.

<!-- SPECS:24 -->
> Equivalent seeds need not select identical stochastic reset traces, but seeded reset distributions and semantics must match the oracle.

Evidence: the live suite's reset workload plus `tests/test_oracle_configuration.py::test_reset_distribution_comparison_rejects_a_wrong_distribution`, `tests/test_oracle_configuration.py::test_reset_distribution_comparison_samples_every_lane`, and `tests/test_oracle_configuration.py::test_aligned_reset_semantics_reject_a_wrong_nondefault_count` guard distribution and aligned semantics.

<!-- SPECS:25 -->
> Changes capable of affecting canonical `Start` physics, rewards, lifecycle, observations, rendering, or shared information must be acceptance-tested side by side against the pinned Stable Retro Turbo oracle.

Evidence: `CONTRIBUTING.md` and `.github/pull_request_template.md` require the fixed `make test-semantic-oracle` gate for semantics-capable changes; `tests/test_oracle_configuration.py::test_pull_request_template_names_the_sole_turbo_oracle_command` prevents checklist drift.

<!-- SPECS:26 -->
> The canonical `Breakout-Atari2600-v0` `Start` state must reproduce the oracle’s 160×210 geometry, 18×6 brick wall, 2×4 ball, initially 16×4 ceiling-narrowing paddle, five-life counter, FIRE-gated serves, paddle inertia, delayed collision latches, breakthrough speed, score raster, scanline priority, and wall and corner behavior.

Evidence: the live Stable Retro Turbo suite covers complete public trajectories; focused guards include `tests/test_env.py::test_render_matches_atari_2600_geometry_and_palette`, `tests/test_env.py::test_render_uses_exact_atari_ball_and_paddle_footprints_at_motion_limits`, `tests/test_env.py::test_atari_digital_paddle_inertia_trace`, `tests/test_env.py::test_delayed_collision_latches_reproduce_the_top_left_corner_trace`, and the `parity_tests` Rust module.

<!-- SPECS:27 -->
> With `noop_reset_max=N`, each selected static reset must reproducibly sample an inclusive `1..N` raw-frame noop count independently of frame skip, must never issue FIRE, and must leave unselected lanes unchanged.

Evidence: `tests/test_env.py::test_seeded_noop_reset_is_reproducible_and_uses_raw_frames`, `tests/test_env.py::test_masked_noop_resets_do_not_advance_other_lanes_random_streams`, and `tests/test_env.py::test_fire_reset_remains_unavailable` cover the public reset semantics; the live reset suite compares them with the oracle.

<!-- SPECS:28 -->
> Rewards must equal the score change over each environment step using Atari row scoring, without life-loss or board-clear shaping.

Evidence: `tests/test_env.py::test_reward_matches_stable_retro_score_delta_by_brick_row`, `tests/test_env.py::test_life_loss_has_no_reward_shaping`, and `tests/test_env.py::test_board_clear_returns_only_the_score_delta_without_bonus` cover each clause.

<!-- SPECS:29 -->
> Clearing the first brick wall must refill the same layout one native frame after the next paddle return.

Evidence: `parity_tests::first_clear_survives_miss_fire_wait_and_refills_after_later_paddle_return` and `parity_tests::custom_layout_refills_its_own_mask` exercise refill timing and layout identity; the live suite covers canonical public signals.

<!-- SPECS:30 -->
> Clearing the second brick wall must leave the board permanently empty at the Atari maximum score of 864.

Evidence: `parity_tests::cartridge_has_two_walls_max_score_864_and_lives_only_termination`, `tests/test_env.py::test_full_wall_info_preserves_all_108_brick_bits_and_wall_progress`, and the live suite cover board state, score, and public information.

<!-- SPECS:31 -->
> Canonical play must terminate only after all five lives are lost, and the environment itself must never generate truncation.

Evidence: `tests/test_env.py::test_life_loss_has_no_reward_shaping`, `tests/test_env.py::test_terminal_lane_requires_explicit_reset_then_can_continue`, `parity_tests::cartridge_has_two_walls_max_score_864_and_lives_only_termination`, and the live suite cover termination and truncation.

<!-- SPECS:32 -->
> Shared information values must match the oracle’s Atari conventions, including reporting inactive `ball_y` as zero.

Evidence: `tests/test_env.py::test_info_presence_masks_follow_the_configured_filter`, `parity_tests::public_ball_y_matches_the_atari_ram_contract`, and the live suite compare the complete shared information surface.

<!-- SPECS:33 -->
> Canonical gameplay semantics and the supported replacement contract must remain protected even when auxiliary public APIs evolve during `0.x`.

Evidence: the public `BreakoutVecEnv` regression suites, fixed sole-oracle workload and attested release verifier, supported-platform trace comparison, and ADR `0001-use-stable-retro-turbo-as-semantic-oracle.md` jointly gate canonical behavior independently of auxiliary API evolution.
