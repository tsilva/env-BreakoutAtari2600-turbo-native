from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


def verifier(monkeypatch):
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "verify_release", scripts / "verify_release.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def pypi_data():
    return {
        "urls": [
            {
                "filename": "example.whl",
                "digests": {"sha256": "abc"},
                "packagetype": "bdist_wheel",
                "yanked": False,
                "url": "https://files.pythonhosted.org/packages/example.whl",
            }
        ]
    }


def test_fresh_download_verification_rejects_different_pypi_digest(monkeypatch):
    module = verifier(monkeypatch)
    with pytest.raises(ValueError, match="hashes differ"):
        module.validate_pypi(pypi_data(), {"example.whl": "different"})


def test_fresh_download_verification_rejects_yanked_file(monkeypatch):
    module = verifier(monkeypatch)
    data = pypi_data()
    data["urls"][0]["yanked"] = True
    with pytest.raises(ValueError, match="yanked"):
        module.validate_pypi(data, {"example.whl": "abc"})


def test_fresh_download_verification_rejects_unexpected_file(monkeypatch):
    module = verifier(monkeypatch)
    data = pypi_data()
    data["urls"].append(data["urls"][0])
    with pytest.raises(ValueError, match="exactly"):
        module.validate_pypi(data, {"example.whl": "abc"})


def test_fresh_download_verification_rejects_untrusted_origin(monkeypatch):
    module = verifier(monkeypatch)
    data = pypi_data()
    data["urls"][0]["url"] = "https://example.com/example.whl"
    with pytest.raises(ValueError, match="download origin"):
        module.validate_pypi(data, {"example.whl": "abc"})


def test_fresh_downloads_require_both_attestation_types(monkeypatch):
    module = verifier(monkeypatch)
    commands = []
    monkeypatch.setattr(
        module.subprocess, "run", lambda args, **kwargs: commands.append(args)
    )
    module.attest(Path("download.whl"), "a" * 40)
    assert len(commands) == 2
    assert all("--source-digest" in command for command in commands)
    assert "https://spdx.dev/Document" in commands[1]
