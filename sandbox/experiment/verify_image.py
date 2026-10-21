"""Offline scientific-image material checks; no project or cloud imports.

This helper is copied only into a separately authorized image build. Importing
it performs no reads or writes. Installer removal requires the exact private
build marker, Linux, explicit environment opt-in and a /usr/local Python prefix.
No function downloads, installs or runs experiment code.
"""

from __future__ import annotations

import argparse
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import sys
import sysconfig

MANDATORY = {
    "numpy",
    "pandas",
    "pyarrow",
    "scipy",
    "statsmodels",
    "matplotlib",
    "packaging",
}
MAX_LOCK_BYTES = 4 * 1024**2
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_VERSION = re.compile(r"^[0-9][A-Za-z0-9.!+_-]{0,127}$")
_HASH = re.compile(r"^[a-f0-9]{64}$")
_BASE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}@sha256:[a-f0-9]{64}$")
_REQUIREMENT = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9_.-]*)==([0-9][A-Za-z0-9.!+_-]*)\s+"
    r"(--hash=sha256:[a-f0-9]{64}(?:\s+--hash=sha256:[a-f0-9]{64})*)$"
)


class MaterialError(ValueError):
    pass


def normalized(name):
    return re.sub(r"[-_.]+", "-", name).lower()


def forbidden(name):
    return name in {
        "pip",
        "setuptools",
        "wheel",
        "fastapi",
        "uvicorn",
        "sqlalchemy",
        "psycopg",
        "psycopg2",
        "psycopg2-binary",
        "asyncpg",
        "pg8000",
        "openai",
        "boto3",
        "botocore",
        "google-auth",
        "google-api-core",
    } or name.startswith(("google-cloud-", "azure-"))


def validate_materials(document, lock_bytes, *, base_reference):
    """Require a dedicated complete pin set, not serving requirements or a tag."""
    try:
        if (
            type(document) is not dict
            or set(document)
            != {
                "version",
                "base_reference",
                "python_version",
                "lockfile_sha256",
                "packages",
            }
            or document["version"] != "c23-scientific-build-v1"
            or type(base_reference) is not str
            or not _BASE.fullmatch(base_reference)
            or base_reference != document["base_reference"]
            or type(document["python_version"]) is not str
            or not re.fullmatch(
                r"3\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", document["python_version"]
            )
            or type(lock_bytes) is not bytes
            or not 1 <= len(lock_bytes) <= MAX_LOCK_BYTES
            or type(document["lockfile_sha256"]) is not str
            or not _HASH.fullmatch(document["lockfile_sha256"])
            or hashlib.sha256(lock_bytes).hexdigest() != document["lockfile_sha256"]
        ):
            raise ValueError
        packages = document["packages"]
        if type(packages) is not dict or not 7 <= len(packages) <= 256:
            raise ValueError
        canonical = {}
        for name, version in packages.items():
            if (
                type(name) is not str
                or not _NAME.fullmatch(name)
                or type(version) is not str
                or not _VERSION.fullmatch(version)
                or normalized(name) in canonical
                or forbidden(normalized(name))
            ):
                raise ValueError
            canonical[normalized(name)] = version
        if not MANDATORY <= canonical.keys():
            raise ValueError
        lines, pending = [], ""
        for raw in lock_bytes.decode("utf-8").splitlines():
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            if line.endswith("\\"):
                pending += line[:-1].strip() + " "
            else:
                lines.append(pending + line)
                pending = ""
        if pending:
            raise ValueError
        observed = {}
        for line in lines:
            match = _REQUIREMENT.fullmatch(line)
            if match is None:
                raise ValueError
            name, version, hashes = match.groups()
            name = normalized(name)
            if name in observed or len(hashes.split()) > 64:
                raise ValueError
            observed[name] = version
        if canonical != observed:
            raise ValueError
        return json.loads(json.dumps(document))
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        raise MaterialError(
            "Scientific build materials are incomplete or not exactly pinned"
        ) from None


def verify_installed(document):
    """Inspect this *image build's* exact package inventory and dependency graph."""
    expected = {
        normalized(name): version for name, version in document["packages"].items()
    }
    if (
        platform.python_version() != document["python_version"]
        or platform.system() != "Linux"
    ):
        raise MaterialError("The image Python/platform does not match its manifest")
    actual, distributions = {}, []
    for item in metadata.distributions():
        name = normalized(item.metadata["Name"])
        if name in actual or forbidden(name):
            raise MaterialError(
                "Unexpected duplicate or excluded installed distribution"
            )
        actual[name] = item.version
        distributions.append(item)
    if actual != expected:
        raise MaterialError(
            "Installed package inventory is not the complete locked manifest"
        )
    # packaging itself must be an exact locked distribution, before this import.
    from packaging.requirements import Requirement
    from packaging.version import Version

    try:
        for item in distributions:
            for text in item.requires or []:
                requirement = Requirement(text)
                if requirement.url:
                    raise ValueError
                if requirement.marker is not None and not requirement.marker.evaluate(
                    {"extra": ""}
                ):
                    continue
                name = normalized(requirement.name)
                if (
                    name not in actual
                    or Version(actual[name]) not in requirement.specifier
                ):
                    raise ValueError
    except (ValueError, KeyError):
        raise MaterialError(
            "A locked installed dependency is missing or incompatible"
        ) from None
    if any(
        (Path(sysconfig.get_path("stdlib")) / name).exists()
        for name in ("ensurepip", "venv")
    ):
        raise MaterialError(
            "Installer/virtual-environment modules remain in the runtime image"
        )
    return {
        "python_version": platform.python_version(),
        "packages": actual,
        "dependency_graph": "verified",
    }


def strip_installers():
    """Build-only cleanup; unavailable in normal host invocation and final image."""
    marker = Path("/opt/ocean-c23-image-build-only")
    if (
        platform.system() != "Linux"
        or os.environ.get("OCEAN_C23_IMAGE_BUILD") != "1"
        or sys.prefix != "/usr/local"
        or not marker.is_file()
        or marker.read_bytes() != b"c23-scientific-image-build\n"
    ):
        raise MaterialError(
            "Installer removal is restricted to the explicit scientific image build"
        )
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    site = Path(sysconfig.get_path("purelib")).resolve()
    scripts = Path(sysconfig.get_path("scripts")).resolve()
    if not all(path.is_relative_to("/usr/local") for path in (stdlib, site, scripts)):
        raise MaterialError("Unexpected Python image installation paths")
    targets = [stdlib / "ensurepip", stdlib / "venv"]
    for path in site.iterdir():
        if path.name in {
            "pip",
            "setuptools",
            "wheel",
            "_distutils_hack",
            "pkg_resources",
            "easy_install.py",
        } or re.fullmatch(
            r"(?:pip|setuptools|wheel)-[^/]+\.(?:dist-info|egg-info)", path.name
        ):
            targets.append(path)
    for path in scripts.iterdir():
        if re.fullmatch(
            r"(?:pip|easy_install)(?:[0-9]+(?:\.[0-9]+)*)?|wheel", path.name
        ):
            targets.append(path)
    for path in targets:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)


def _read_bounded(path, maximum):
    if not path.is_file() or path.is_symlink() or path.stat().st_size > maximum:
        raise MaterialError("Image material file is missing or exceeds its bound")
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise MaterialError("Image material file exceeds its bound")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument("--check-materials", action="store_true")
    operation.add_argument("--verify-installed", action="store_true")
    operation.add_argument("--strip-installers", action="store_true")
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--base-reference", required=True)
    args = parser.parse_args()
    document = validate_materials(
        json.loads(_read_bounded(args.manifest, 1024**2)),
        _read_bounded(args.lock, MAX_LOCK_BYTES),
        base_reference=args.base_reference,
    )
    if args.strip_installers:
        strip_installers()
    result = (
        verify_installed(document)
        if args.verify_installed
        else {"materials": "verified"}
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except (MaterialError, OSError, ValueError, KeyError) as error:
        raise SystemExit(str(error)) from None
