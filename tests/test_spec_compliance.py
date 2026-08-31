from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_cross_provider_parity_is_delegated_to_turbobench() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "$(TURBOBENCH) parity breakout/start-v2" in makefile
    assert "--candidate env-breakoutatari2600-turbo-native@checkout:" in makefile
    assert "--candidate env-breakoutatari2600-turbo-native@artifact:" in makefile
    assert "verify-parity" in makefile
    assert "compare_stable_retro_turbo.py" not in makefile


def test_repository_has_no_cross_provider_comparator() -> None:
    forbidden = {
        "scripts/compare_stable_retro_turbo.py",
        "scripts/oracle_release_gate.py",
        "tests/test_stable_retro_turbo_oracle.py",
        "tests/test_oracle_configuration.py",
        "tests/test_oracle_release_gate.py",
    }
    assert all(not (ROOT / path).exists() for path in forbidden)


def test_release_workflow_reuses_the_certified_exact_wheel() -> None:
    parity = (ROOT / ".github/workflows/parity-evidence.yml").read_text(encoding="utf-8")
    release = (ROOT / ".github/workflows/release-build.yml").read_text(encoding="utf-8")
    assert "@artifact:${wheel[0]}" in parity
    assert "verify-parity parity-evidence/receipt --require-canonical" in parity
    assert "cp parity-evidence/*.whl candidate/dist/" in release
    assert "turbobench-parity-receipt.tar.gz" in release


def test_private_assets_stay_out_of_distributions() -> None:
    manifest = ROOT / "validation/parity-assets.json"
    assert manifest.is_file()
    assert not (ROOT / "validation/oracle-roms.json").exists()
    assert not any((ROOT / "python").rglob("rom.a26"))
