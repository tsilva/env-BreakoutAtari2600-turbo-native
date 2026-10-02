#!/usr/bin/env python3
"""Verify fresh public release downloads against the attested candidate."""

from __future__ import annotations

import argparse
import json
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from release_state import PACKAGE, REPOSITORY, sha256, verify_candidate


def github_json(endpoint: str) -> dict:
    return json.loads(subprocess.check_output(["gh", "api", endpoint], text=True))


def attest(distribution: Path, commit: str) -> None:
    command = [
        "gh",
        "attestation",
        "verify",
        str(distribution),
        "--repo",
        REPOSITORY,
        "--signer-workflow",
        f"{REPOSITORY}/.github/workflows/release-build.yml",
        "--source-digest",
        commit,
        "--deny-self-hosted-runners",
    ]
    subprocess.run(command, check=True)
    subprocess.run(
        command + ["--predicate-type", "https://spdx.dev/Document"], check=True
    )


def validate_pypi(data: dict, expected: dict[str, str]) -> list[dict]:
    files = data.get("urls", [])
    if len(files) != len(expected):
        raise ValueError(
            "PyPI does not contain exactly the three candidate distributions"
        )
    actual = {}
    for item in files:
        name = item["filename"]
        if item.get("yanked") or name in actual:
            raise ValueError("PyPI contains yanked or duplicate distributions")
        kind = "bdist_wheel" if name.endswith(".whl") else "sdist"
        if item.get("packagetype") != kind:
            raise ValueError("PyPI distribution type differs from candidate")
        url = urllib.parse.urlparse(item["url"])
        if url.scheme != "https" or url.hostname != "files.pythonhosted.org":
            raise ValueError("unexpected PyPI download origin")
        actual[name] = item["digests"]["sha256"]
    if actual != expected:
        raise ValueError("PyPI file names or hashes differ from the candidate")
    return files


def verify(args: argparse.Namespace) -> dict:
    manifest = verify_candidate(
        args.candidate,
        version=args.version,
        commit=args.commit,
        repository=REPOSITORY,
        run_id=args.run_id,
    )
    expected = {
        Path(item["path"]).name: item["sha256"]
        for item in manifest["artifacts"]
        if item["path"].startswith("dist/")
    }
    # mkdir without exist_ok requires a fresh verification directory.
    args.output.mkdir(parents=True)
    pypi_dir = args.output / "pypi"
    pypi_dir.mkdir()
    with urllib.request.urlopen(
        f"https://pypi.org/pypi/{PACKAGE}/{args.version}/json", timeout=30
    ) as response:
        data = json.load(response)
    for item in validate_pypi(data, expected):
        distribution = pypi_dir / item["filename"]
        with urllib.request.urlopen(item["url"], timeout=60) as response:
            distribution.write_bytes(response.read())
        if sha256(distribution) != expected[distribution.name]:
            raise ValueError(f"fresh PyPI download hash mismatch: {distribution.name}")
        attest(distribution, args.commit)

    tag = f"v{args.version}"
    ref = github_json(f"repos/{REPOSITORY}/git/ref/tags/{tag}")
    if (
        ref.get("object", {}).get("type") != "commit"
        or ref["object"].get("sha") != args.commit
    ):
        raise ValueError("release tag does not point to the exact candidate commit")
    release = github_json(f"repos/{REPOSITORY}/releases/tags/{tag}")
    if not release.get("immutable") or release.get("draft"):
        raise ValueError("GitHub Release is not published and immutable")
    expected_assets = {
        path.name: path for path in args.candidate.rglob("*") if path.is_file()
    }
    assets = release.get("assets", [])
    if len(assets) != 7 or {item["name"] for item in assets} != set(expected_assets):
        raise ValueError(
            "GitHub Release does not contain the exact seven candidate files"
        )
    github_dir = args.output / "github"
    github_dir.mkdir()
    subprocess.run(
        [
            "gh",
            "release",
            "download",
            tag,
            "--repo",
            REPOSITORY,
            "--dir",
            str(github_dir),
        ],
        check=True,
    )
    for name, source in expected_assets.items():
        if sha256(github_dir / name) != sha256(source):
            raise ValueError(f"GitHub Release asset differs from candidate: {name}")
    result = {
        "version": args.version,
        "tag": tag,
        "commit": args.commit,
        "candidate_run_id": args.run_id,
        "distributions": expected,
        "github_release": release["html_url"],
        "pypi": f"https://pypi.org/project/{PACKAGE}/{args.version}/",
        "verified": True,
    }
    (args.output / "verification.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(verify(parser.parse_args()), indent=2))


if __name__ == "__main__":
    main()
