# Training on native Breakout

## Train an agent

Train a PPO agent with the published [GradLab](https://github.com/tsilva/gradlab)
recipes. Training lives in GradLab, separately from this environment. Run either
version-pinned recipe from any directory:

```bash
# Standard PPO
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo

# PPO with learning-rate decay and KL-based update stopping
uvx gradlab@0.1.1 train Breakout-Atari2600-v0/ppo-stable-updates
```

These are full training runs. GradLab saves `final_model.zip` under `./runs`
and prints a version-pinned playback command when training finishes or stops safely. Run that
command to watch your trained policy play. Local runs disable W&B and checkpoint
evaluation by default.

## Use from Python

Save this as `quickstart.py` in your project, then run `uv run python quickstart.py`:

```python
import gymnasium as gym
import numpy as np

env = gym.make_vec(
    "env_breakoutatari2600_turbo_native:EnvBreakoutAtari2600TurboNative-v0",
    game="Breakout-Atari2600-v0",
    num_envs=16,
    num_threads=4,
)

try:
    obs, infos = env.reset(seed=42)
    actions = np.ones(env.num_envs, dtype=np.uint8)  # FIRE in every game
    obs, rewards, terminated, truncated, infos = env.step(actions)
    print(obs.shape)  # (16, 4, 84, 84)
finally:
    env.close()
```

This starts 16 independent games and serves the ball in each. Observations
contain four stacked 84×84 grayscale frames per game. Each step advances four
native game frames by default.

See the [full rollout example](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/examples/quickstart.py)
for a longer loop with selective resets and a local throughput measurement.
