"""Check release archives for required metadata and accidental private data."""

from __future__ import annotations

import argparse
import os
import re
import tarfile
import tomllib
import zipfile
from pathlib import Path

TOKEN_PATTERNS = (
    re.compile(rb"sk-or-v1-[A-Za-z0-9_-]{12,}"),
    re.compile(rb"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
)


def _members(path: Path) -> dict[str, bytes]:
    if path.suffix == ".whl":
        with zipfile.ZipFile(path) as archive:
            return {name: archive.read(name) for name in archive.namelist()}
    if path.name.endswith(".tar.gz"):
        with tarfile.open(path, "r:gz") as archive:
            return {
                member.name: archive.extractfile(member).read()
                for member in archive.getmembers()
                if member.isfile()
            }
    raise ValueError(f"Unsupported distribution: {path.name}")


def _secret_values(config_path: Path | None) -> tuple[bytes, ...]:
    if config_path is None:
        return ()
    import yaml

    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    return tuple(
        value.encode("utf-8")
        for provider in config.get("providers", {}).values()
        if isinstance(provider, dict)
        for value in (provider.get("api_key"),)
        if isinstance(value, str) and len(value) >= 8 and not value.startswith("${")
    )


def audit_archive(path: Path, *, version: str, secrets: tuple[bytes, ...]) -> None:
    members = _members(path)
    names = tuple(name.replace("\\", "/") for name in members)
    if any("/scratch/" in f"/{name}" or "/.venv/" in f"/{name}" for name in names):
        raise ValueError(f"Private directory included in {path.name}")
    if any(name.endswith("/.env") or name.endswith(".env.local") for name in names):
        raise ValueError(f"Environment file included in {path.name}")

    payloads = tuple(members.values())
    home = os.environ.get("USERPROFILE") or os.environ.get("HOME")
    forbidden = list(secrets)
    if home:
        forbidden.extend((home.encode(), home.replace("\\", "/").encode()))
    if any(
        secret and secret in content for secret in forbidden for content in payloads
    ):
        raise ValueError(f"Private value included in {path.name}")
    if any(
        pattern.search(content) for pattern in TOKEN_PATTERNS for content in payloads
    ):
        raise ValueError(f"Credential-like token included in {path.name}")

    metadata_name = next(
        (
            name
            for name in members
            if name.endswith("/METADATA") or name.endswith("/PKG-INFO")
        ),
        None,
    )
    if metadata_name is None:
        raise ValueError(f"Missing package metadata in {path.name}")
    metadata = members[metadata_name].decode("utf-8")
    if f"Version: {version}" not in metadata:
        raise ValueError(f"Wrong version in {path.name}")
    if "License-Expression: MIT" not in metadata:
        raise ValueError(f"Missing MIT license expression in {path.name}")
    if not any(name == "LICENSE" or name.endswith("/LICENSE") for name in names):
        raise ValueError(f"Missing LICENSE in {path.name}")
    if path.name.endswith(".tar.gz") and not any(
        name.endswith("/CHANGELOG.md") for name in names
    ):
        raise ValueError(f"Missing CHANGELOG in {path.name}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path, nargs="?", default=Path("dist"))
    parser.add_argument("--secret-config", type=Path)
    args = parser.parse_args()
    project = tomllib.loads(Path("pyproject.toml").read_text(encoding="utf-8"))
    version = project["project"]["version"]
    artifacts = sorted(args.directory.glob(f"moiryx-{version}*.whl")) + sorted(
        args.directory.glob(f"moiryx-{version}*.tar.gz")
    )
    if len(artifacts) != 2:
        raise SystemExit(f"Expected one wheel and one sdist for {version}")
    secrets = _secret_values(args.secret_config)
    for artifact in artifacts:
        audit_archive(artifact, version=version, secrets=secrets)
        print(f"audited: {artifact.name}")


if __name__ == "__main__":
    main()
