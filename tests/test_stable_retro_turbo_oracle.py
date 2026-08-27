"""Live differential validation against the pinned Stable Retro Turbo oracle."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

pytestmark = pytest.mark.stable_retro


def test_representative_canonical_trajectories_match_pinned_turbo_provider():
    from compare_stable_retro_turbo import PreflightError, preflight, run_live_suite

    provider_repo = Path(
        os.environ.get(
            "BREAKOUT_STABLE_RETRO_TURBO_REPO",
            REPO_ROOT.parent / "env-StableRetro-turbo",
        )
    )
    data_root_value = os.environ.get("RETRO_DATA_PATH")
    data_root = Path(data_root_value) if data_root_value else None
    try:
        inputs = preflight(provider_repo, data_root)
        report = run_live_suite(inputs, steps=2_048)
    except PreflightError as error:
        if os.environ.get("BREAKOUT_REQUIRE_STABLE_RETRO_TURBO") == "1":
            pytest.fail(str(error), pytrace=False)
        pytest.skip(str(error))

    assert report["provider"]["module"] == "env_stableretro_turbo"
    assert report["provider"]["turbo_api_version"] == 2
    assert report["aligned_reset"]["exact"]
    assert report["seeded_reset_noops"]["exact"]
    distribution = report["seeded_reset_noops"]["distribution"]
    assert distribution["sample_count"] == 512
    assert distribution["lane_sample_count"] == 256
    assert distribution["lane_count"] == 2
    assert distribution["seed_corpus"] == [0, 255]
    assert distribution["maximum_cdf_distance"] == 0.15
    assert distribution["matches"]
    assert [lane["lane"] for lane in distribution["lanes"]] == [0, 1]
    assert report["seeded_reset_noops"]["counts"] == list(range(1, 31))
    assert report["trajectories"]["cycling"]["exact"]
    assert report["trajectories"]["seeded-random"]["exact"]
