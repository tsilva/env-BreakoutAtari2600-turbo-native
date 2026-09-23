"""Run a short, ROM-free vector rollout with the published package."""

from time import perf_counter

import gymnasium as gym
import numpy as np

env = gym.make_vec(
    "env_breakoutatari2600_turbo_native:EnvBreakoutAtari2600TurboNative-v0",
    game="Breakout-Atari2600-v0",
    num_envs=16,
    num_threads=4,
)

try:
    obs, _ = env.reset(seed=42)
    total_reward = 0.0
    started = perf_counter()
    for step in range(1024):
        # This fixed action cycle is a smoke workload, not a trained policy.
        action = 1 if step % 4 == 0 else 2
        actions = np.full(env.num_envs, action, dtype=np.uint8)
        obs, rewards, terminated, truncated, _ = env.step(actions)
        total_reward += float(rewards.sum())
        done = terminated | truncated
        if done.any():
            obs, _ = env.reset(options={"reset_mask": done})
    elapsed = perf_counter() - started
    print(f"observation shape: {obs.shape}")
    print(f"total reward: {total_reward:g}")
    print(f"transitions: {1024 * env.num_envs}")
    print(f"transitions/second: {1024 * env.num_envs / elapsed:,.0f} (local diagnostic)")
finally:
    env.close()
