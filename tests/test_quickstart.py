from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_readme_python_example_runs():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    block = re.search(r"## Use from Python\n.*?```python\n(.*?)\n```", readme, re.S)
    assert block is not None
    result = subprocess.run(
        [sys.executable, "-c", block.group(1)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert result.stdout.strip() == "(16, 4, 84, 84)"


def test_quickstart_runs_a_scoring_vector_rollout():
    result = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "quickstart.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert "observation shape: (16, 4, 84, 84)" in result.stdout
    assert "transitions: 16384" in result.stdout
    reward = re.search(r"total reward: ([0-9.]+)", result.stdout)
    assert reward is not None and float(reward.group(1)) > 0
    assert "transitions/second:" in result.stdout
