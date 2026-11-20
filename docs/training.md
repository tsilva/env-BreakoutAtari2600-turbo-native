# Training on native Breakout

## Train an agent

Train a PPO agent with the published [GradLab](https://github.com/tsilva/gradlab)
recipes. Training lives in GradLab, separately from this environment. Run either
version-pinned recipe from any directory:

See the [pinned PPO recipes](../README.md#train-an-agent).

These are full training runs. GradLab saves `final_model.zip` under `./runs`
and prints a version-pinned playback command when training finishes or stops safely. Run that
command to watch your trained policy play. Local runs disable W&B and checkpoint
evaluation by default.

## Use from Python

Save this as `quickstart.py` in your project, then run `uv run python quickstart.py`:

See the [README Python example](../README.md#use-from-python).

This starts 16 independent games and serves the ball in each. Observations
contain four stacked 84×84 grayscale frames per game. Each step advances four
native game frames by default.

See the [full rollout example](https://github.com/tsilva/env-BreakoutAtari2600-turbo-native/blob/main/examples/quickstart.py)
for a longer loop with selective resets and a local throughput measurement.
