from __future__ import annotations

import copy
import importlib.util
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

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
    provider = gate.receipt_provider(PIN)
    del provider["repository"]
    provider.update(
        installed_record_sha256="e" * 64,
        artifact_sha256="f" * 64,
        artifact_source="isolated-pinned-wheel",
    )
    return {"provider": provider, "workloads": workloads}


def exact_receipt(gate):
    candidate = {
        "kind": "checkout",
        "package": gate.CANDIDATE_PACKAGE,
        "version": VERSION,
        "commit": COMMIT,
        "installed_record_sha256": "c" * 64,
        "artifact": {"source": "locally-built-wheel", "sha256": "d" * 64},
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


@pytest.mark.parametrize("field", ["distribution", "version", "revision", "tree"])
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


@pytest.mark.parametrize(
    ("steps", "completion", "completed"),
    [
        (1, "episode-ended", [1]),
        (2_047, "episode-ended", [1]),
        (2_047, "step-limit", [0]),
    ],
)
def test_receipt_rejects_truncated_nonzero_workload(steps, completion, completed):
    gate = module()
    receipt = exact_receipt(gate)
    trajectory = receipt["comparison"]["report"]["workloads"]["one-lane"][
        "trajectories"
    ]["cycling"]
    trajectory.update(
        steps=steps,
        completion=completion,
        completed_episodes=completed,
    )

    with pytest.raises(ValueError, match="fixed workload"):
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


def test_receipt_loader_rejects_duplicate_json_keys(tmp_path):
    gate = module()
    receipt = tmp_path / "receipt.json"
    receipt.write_text('{"schema":1,"schema":1}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate JSON key.*schema"):
        gate.load_receipt(receipt)


def test_release_verifier_rejects_unattested_synthetic_receipt(tmp_path, monkeypatch):
    gate = module()
    receipt = tmp_path / "synthetic.json"
    gate.write_receipt(receipt, exact_receipt(gate))
    monkeypatch.setattr(
        gate.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "no attestation"),
    )

    with pytest.raises(ValueError, match="lacks trusted GitHub provenance"):
        gate.verify_release_attestation(receipt, "owner/repository", COMMIT)


def test_release_verifier_binds_oracle_workflow_source_and_hosted_runner(
    tmp_path, monkeypatch
):
    gate = module()
    receipt = tmp_path / "receipt.json"
    receipt.write_text("{}", encoding="utf-8")
    calls = []

    def run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, "verified", "")

    monkeypatch.setattr(gate.subprocess, "run", run)

    gate.verify_release_attestation(receipt, "owner/repository", COMMIT)

    assert calls == [
        [
            "gh",
            "attestation",
            "verify",
            str(receipt),
            "--repo",
            "owner/repository",
            "--signer-workflow",
            "owner/repository/.github/workflows/oracle-evidence.yml",
            "--source-digest",
            COMMIT,
            "--deny-self-hosted-runners",
        ]
    ]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifact_source", "diagnostic"),
        ("artifact_sha256", "not-a-digest"),
        ("installed_record_sha256", None),
    ],
)
def test_receipt_rejects_unbound_provider_runtime(field, value):
    gate = module()
    receipt = exact_receipt(gate)
    receipt["comparison"]["report"]["provider"][field] = value

    with pytest.raises(ValueError, match="provider"):
        verify(gate, receipt)


def test_candidate_install_rejects_shadowed_ambient_module(tmp_path, monkeypatch):
    gate = module()
    installed = tmp_path / "site-packages" / gate.CANDIDATE_MODULE
    installed.mkdir(parents=True)
    shadow = tmp_path / "shadow" / gate.CANDIDATE_MODULE / "__init__.py"
    shadow.parent.mkdir(parents=True)
    shadow.write_text("shadow\n", encoding="utf-8")
    distribution = SimpleNamespace(
        locate_file=lambda path: tmp_path / "site-packages" / path,
        read_text=lambda name: None,
        files=[],
    )
    monkeypatch.setattr(
        gate.importlib.metadata, "distribution", lambda _name: distribution
    )
    monkeypatch.setattr(
        gate.importlib,
        "import_module",
        lambda _name: SimpleNamespace(__file__=str(shadow), __version__=VERSION),
    )
    monkeypatch.setattr(gate, "verify_installed_distribution", lambda _dist: "a" * 64)

    with pytest.raises(ValueError, match="ambient candidate module"):
        gate.candidate_distribution_identity("published-distribution")


def test_checkout_candidate_rejects_installed_source_substitution(tmp_path, monkeypatch):
    gate = module()
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    source = tmp_path / "python" / gate.CANDIDATE_MODULE / "__init__.py"
    source.parent.mkdir(parents=True)
    source.write_text("PINNED = True\n", encoding="utf-8")
    installed_root = tmp_path / "site-packages"
    installed = installed_root / gate.CANDIDATE_MODULE / "__init__.py"
    installed.parent.mkdir(parents=True)
    installed.write_text("PINNED = False\n", encoding="utf-8")
    distribution = SimpleNamespace(
        locate_file=lambda path: installed_root / path,
    )

    with pytest.raises(ValueError, match="does not match checkout"):
        gate.verify_checkout_source_binding(distribution)


def test_published_candidate_rejects_substituted_wheel_identity(tmp_path, monkeypatch):
    gate = module()
    installed = tmp_path / "site-packages" / gate.CANDIDATE_MODULE
    installed.mkdir(parents=True)
    module_path = installed / "__init__.py"
    module_path.write_text("installed\n", encoding="utf-8")
    substitute = tmp_path / "substitute.whl"
    substitute.write_bytes(b"substitute")
    distribution = SimpleNamespace(
        locate_file=lambda path: tmp_path / "site-packages" / path,
        read_text=lambda name: json.dumps({"url": substitute.as_uri()}),
        files=[],
    )
    monkeypatch.setattr(
        gate.importlib.metadata, "distribution", lambda _name: distribution
    )
    monkeypatch.setattr(
        gate.importlib.metadata, "version", lambda _name: VERSION
    )
    monkeypatch.setattr(
        gate.importlib,
        "import_module",
        lambda _name: SimpleNamespace(__file__=str(module_path), __version__=VERSION),
    )
    monkeypatch.setattr(gate, "verify_installed_distribution", lambda _dist: "a" * 64)

    with pytest.raises(ValueError, match="wheel identity"):
        gate.candidate_distribution_identity("published-distribution")
