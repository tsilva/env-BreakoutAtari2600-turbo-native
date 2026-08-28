from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "oracle_release_gate.py"
PIN = json.loads(
    (REPO_ROOT / "validation/stable-retro-turbo.json").read_text(encoding="utf-8")
)
COMMIT = "a" * 40
VERSION = "1.2.3"


def module():
    spec = importlib.util.spec_from_file_location("oracle_release_gate", SCRIPT)
    assert spec is not None and spec.loader is not None
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def exact_report(gate):
    workloads = {}
    for name, lane_count in gate.LIVE_WORKLOADS:
        workloads[name] = {
            "lane_count": lane_count,
            "aligned_reset": {"exact": True},
            "trajectories": {
                trajectory_name: {
                    "exact": True,
                    "complete": True,
                    "completion": "step-limit",
                    "steps": gate.CANONICAL_STEPS,
                    "maximum_steps": gate.CANONICAL_STEPS,
                    "completed_episodes": [0] * lane_count,
                }
                for trajectory_name in gate.REQUIRED_TRAJECTORIES
            },
            "seeded_reset_noops": {
                "exact": True,
                "counts": list(range(1, 31)),
                "distribution": {
                    "matches": True,
                    "lane_count": lane_count,
                    "lane_sample_count": len(gate.RESET_DISTRIBUTION_SEEDS),
                    "seed_corpus": [0, 255],
                    "maximum": 30,
                },
            },
        }
    return {"provider": gate.receipt_provider(PIN), "workloads": workloads}


def exact_receipt(gate):
    candidate = {
        "kind": "checkout",
        "package": gate.CANDIDATE_PACKAGE,
        "version": VERSION,
        "commit": COMMIT,
    }
    return gate.create_receipt(
        provider=PIN,
        candidate=candidate,
        report=exact_report(gate),
    )


def verify(gate, receipt):
    return gate.verify_receipt(
        receipt,
        candidate_version=VERSION,
        candidate_commit=COMMIT,
    )


def test_receipt_binds_provider_candidate_workload_configuration_and_result():
    gate = module()
    receipt = exact_receipt(gate)

    assert verify(gate, receipt) == receipt
    assert receipt["provider"] == gate.receipt_provider(PIN)
    assert receipt["candidate"]["commit"] == COMMIT
    assert receipt["workload"] == gate.canonical_workload()
    assert receipt["comparison"]["result"] == "exact"


@pytest.mark.parametrize("field", ["distribution", "version", "revision"])
def test_receipt_rejects_missing_or_wrong_provider(field):
    gate = module()
    receipt = exact_receipt(gate)
    receipt["provider"][field] = "wrong"

    with pytest.raises(ValueError, match="provider pin"):
        verify(gate, receipt)


def test_receipt_generation_fails_without_lawful_rom(tmp_path, monkeypatch):
    gate = module()
    monkeypatch.setattr(
        gate.comparison,
        "preflight",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            gate.comparison.PreflightError("lawful Breakout oracle data is incomplete")
        ),
    )

    with pytest.raises(gate.comparison.PreflightError, match="lawful Breakout"):
        gate.generate_receipt(
            provider_repo=tmp_path / "provider",
            data_root=tmp_path / "data",
            candidate_selector="checkout",
            candidate_commit=COMMIT,
        )


def test_certifying_candidate_rejects_diagnostic_override():
    gate = module()

    with pytest.raises(ValueError, match="diagnostic candidate override"):
        gate.candidate_identity("path:/tmp/checkout", candidate_commit=COMMIT)


def test_checkout_candidate_rejects_dirty_tree(tmp_path, monkeypatch):
    gate = module()
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(gate, "git_output", lambda *_args: " M src/lib.rs")

    with pytest.raises(ValueError, match="clean candidate checkout"):
        gate.candidate_identity("checkout", candidate_commit=COMMIT)


def test_receipt_rejects_incomplete_workload():
    gate = module()
    receipt = exact_receipt(gate)
    del receipt["comparison"]["report"]["workloads"]["multi-lane"]

    with pytest.raises(ValueError, match="canonical workloads"):
        verify(gate, receipt)


def test_receipt_rejects_collect_only_style_zero_workload():
    gate = module()
    receipt = exact_receipt(gate)
    trajectory = receipt["comparison"]["report"]["workloads"]["one-lane"][
        "trajectories"
    ]["cycling"]
    trajectory["steps"] = 0

    with pytest.raises(ValueError, match="executed no steps"):
        verify(gate, receipt)


def test_receipt_rejects_mismatched_candidate():
    gate = module()
    receipt = exact_receipt(gate)

    with pytest.raises(ValueError, match="candidate commit"):
        gate.verify_receipt(
            receipt,
            candidate_version=VERSION,
            candidate_commit="b" * 40,
        )


def test_receipt_rejects_trajectory_mismatch():
    gate = module()
    receipt = exact_receipt(gate)
    receipt["comparison"]["result"] = "mismatch"

    with pytest.raises(ValueError, match="comparison result"):
        verify(gate, receipt)


def test_receipt_rejects_modified_canonical_configuration():
    gate = module()
    receipt = exact_receipt(gate)
    receipt["workload"] = copy.deepcopy(receipt["workload"])
    receipt["workload"]["steps_per_trajectory"] = 1

    with pytest.raises(ValueError, match="canonical workload"):
        verify(gate, receipt)


def test_certifying_command_help_has_no_workload_or_pytest_override():
    gate = module()
    help_text = gate.parser().format_help()
    generate_help = gate.parser()._subparsers._group_actions[0].choices[
        "generate"
    ].format_help()

    assert "sole Stable Retro Turbo" in help_text
    assert "fixed certifying workload" in generate_help
    assert "--steps" not in generate_help
    assert "PYTEST_ARGS" not in generate_help
