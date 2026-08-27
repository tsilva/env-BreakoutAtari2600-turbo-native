from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "deterministic_trace.py"


def _load_trace_module():
    spec = importlib.util.spec_from_file_location("deterministic_trace", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_public_trace_is_invariant_across_supported_execution_shapes():
    trace = _load_trace_module().generate_trace("test-platform")

    assert trace["coverage"] == [
        "transitions",
        "observations",
        "rewards",
        "lifecycle_flags",
        "shared_information",
        "serialized_snapshot_continuation",
    ]
    assert set(trace["shape_digests"]) == {
        "scalar",
        "batch",
        "active_neighbors",
        "reordered_lanes",
        "parallel_threads",
    }
    assert len(set(trace["shape_digests"].values())) == 1
    assert trace["trace"][0]["kind"] == "reset"
    transition = trace["trace"][1]
    assert transition["kind"] == "transition"
    assert set(transition) == {
        "kind",
        "step",
        "observation",
        "reward",
        "terminated",
        "truncated",
        "infos",
    }
    assert trace["snapshot_continuation"]["verified"] is True
    assert trace["snapshot_continuation"]["from_step"] > 0


def test_platform_comparison_names_first_divergent_public_value(tmp_path):
    module = _load_trace_module()
    macos = module.generate_trace("macos-arm64")
    linux = copy.deepcopy(macos)
    linux["platform"] = "linux-x86_64"
    linux["trace"][3]["reward"] = "0x1.0000000000000p+0"
    linux["trace_digest"] = module.trace_digest(linux["trace"])
    macos_path = tmp_path / "macos.json"
    linux_path = tmp_path / "linux.json"
    macos_path.write_text(json.dumps(macos), encoding="utf-8")
    linux_path.write_text(json.dumps(linux), encoding="utf-8")

    with pytest.raises(
        module.TraceMismatch,
        match=(
            r"macos-arm64.*linux-x86_64.*trace\[3\]\.reward.*"
            r"0x1\.0000000000000p\+0"
        ),
    ):
        module.compare_trace_files([macos_path, linux_path])


def test_ci_compares_fresh_supported_platform_traces():
    workflow = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert "determinism-trace:" in workflow
    assert "platform: macos-arm64" in workflow
    assert "runner: macos-15" in workflow
    assert "platform: linux-x86_64" in workflow
    assert "runner: ubuntu-24.04" in workflow
    assert "scripts/deterministic_trace.py generate" in workflow
    assert "scripts/deterministic_trace.py compare" in workflow
    assert "needs: determinism-trace" in workflow
    assert "actions/upload-artifact@" in workflow
    assert "actions/download-artifact@" in workflow
