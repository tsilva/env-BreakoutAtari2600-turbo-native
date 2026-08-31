# Breakout Vector Environment

This context defines the language used for the ROM-free vector environment and its compatibility boundaries.

## Language

**Lane**:
One independently stepped Breakout game within the vector environment.
_Avoid_: Game instance, sub-environment

**Canonical `Start`**:
The catalog state named `Start` for `Breakout-Atari2600-v0`, whose cross-provider behavior is checked by TurboBench.
_Avoid_: Full start, default start, starting state

**Native indexed frame**:
The 160×210 source raster shared by policy-observation preprocessing and visual rendering.
_Avoid_: Rendered frame, policy frame

**Rendered frame**:
The canonical 160×210 Stella RGB output derived from a native indexed frame.
_Avoid_: Native frame, indexed frame

**Policy observation**:
The policy-facing output derived from a native indexed frame through observation preprocessing.
_Avoid_: Rendered frame, native frame

**Environment step**:
One batched transition of every lane, potentially advancing each lane through multiple native console frames.
_Avoid_: Native frame, frame

**Native action**:
One integer from the convenience action interface: noop, FIRE, right, or left.
_Avoid_: Filtered action, button vector

**Filtered action**:
One Stable-compatible eight-button vector whose exact row represents noop, FIRE, right, or left; other rows are unsupported.
_Avoid_: Native action, normalized action

**Parity authority**:
The original Stable Retro release pinned by TurboBench's immutable profile.
_Avoid_: Choosing an authority inside this repository

**Serialized snapshot**:
Opaque bytes that preserve exact continuation within the same package version and a compatible environment configuration.
_Avoid_: Live snapshot handle

**Live snapshot handle**:
Session-local state owned by its originating environment and valid only during that environment's lifecycle.
_Avoid_: Serialized snapshot

**Core vector environment**:
The manual-reset vector environment whose lanes expose terminal state until callers reset them.
_Avoid_: SB3 adapter

**SB3 adapter**:
An explicit integration layer that translates core vector-environment behavior into Stable-Baselines3 auto-reset semantics.
_Avoid_: Core vector environment

**Python distribution**:
The installable package published through Python package infrastructure.
_Avoid_: Supported binary platform

**Supported binary platform**:
An operating-system and processor-architecture pair for which the project supports native binaries.
_Avoid_: Python distribution
