"""Release archive audit rejects secrets and missing legal metadata."""

from __future__ import annotations

import tarfile
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from scripts.audit_artifacts import audit_archive

VERSION = "0.1.0a1"
METADATA = f"Name: moiryx\nVersion: {VERSION}\nLicense-Expression: MIT\n".encode()


def _wheel(path: Path, *, source: bytes = b"safe") -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("moiryx/__init__.py", source)
        archive.writestr(f"moiryx-{VERSION}.dist-info/METADATA", METADATA)
        archive.writestr(f"moiryx-{VERSION}.dist-info/licenses/LICENSE", "MIT")


def test_wheel_audit_accepts_safe_archive(tmp_path: Path) -> None:
    path = tmp_path / f"moiryx-{VERSION}-py3-none-any.whl"
    _wheel(path)

    audit_archive(path, version=VERSION, secrets=())


def test_wheel_audit_rejects_known_secret(tmp_path: Path) -> None:
    path = tmp_path / f"moiryx-{VERSION}-py3-none-any.whl"
    _wheel(path, source=b"sentinel-private-key")

    with pytest.raises(ValueError, match="Private value"):
        audit_archive(path, version=VERSION, secrets=(b"sentinel-private-key",))


def test_wheel_audit_rejects_token_pattern(tmp_path: Path) -> None:
    path = tmp_path / f"moiryx-{VERSION}-py3-none-any.whl"
    _wheel(path, source=b"sk-or-v1-" + b"abcdefghijklmnopqrstuvwx")

    with pytest.raises(ValueError, match="Credential-like token"):
        audit_archive(path, version=VERSION, secrets=())


def _sdist(
    path: Path, *, include_scratch: bool = False, include_changelog: bool = True
) -> None:
    entries = [
        (f"moiryx-{VERSION}/PKG-INFO", METADATA),
        (f"moiryx-{VERSION}/LICENSE", b"MIT"),
    ]
    if include_changelog:
        entries.append((f"moiryx-{VERSION}/CHANGELOG.md", b"Changes"))
    if include_scratch:
        entries.append((f"moiryx-{VERSION}/scratch/key.txt", b"private"))
    with tarfile.open(path, "w:gz") as archive:
        for name, content in entries:
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, BytesIO(content))


def test_sdist_audit_checks_changelog_and_excludes_scratch(tmp_path: Path) -> None:
    path = tmp_path / f"moiryx-{VERSION}.tar.gz"
    _sdist(path)
    audit_archive(path, version=VERSION, secrets=())

    _sdist(path, include_scratch=True)
    with pytest.raises(ValueError, match="Private directory"):
        audit_archive(path, version=VERSION, secrets=())

    _sdist(path, include_changelog=False)
    with pytest.raises(ValueError, match="Missing CHANGELOG"):
        audit_archive(path, version=VERSION, secrets=())
