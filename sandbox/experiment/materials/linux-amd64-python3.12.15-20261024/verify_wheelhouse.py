"""Inspect exact downloaded wheel bytes and the declared Linux dependency graph.

This preparation tool needs packaging in its own trusted interpreter. It never
imports a wheel, installs it, or substitutes for Linux installed-image checks.
"""

from __future__ import annotations

import argparse
from email.parser import BytesParser
import json
from pathlib import Path
import zipfile

from packaging.requirements import Requirement
from packaging.specifiers import SpecifierSet
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

from assemble_context import MATERIALS, MAX_WHEEL_BYTES, read_regular, sha


MANDATORY = {"numpy", "pandas", "pyarrow", "scipy", "statsmodels", "matplotlib", "packaging"}


def inspect(wheels):
    materials = json.loads(read_regular(MATERIALS / "build-materials.json", 1024**2))
    inventory = json.loads(read_regular(MATERIALS / "wheels.json", 4 * 1024**2))
    records = inventory["wheels"]
    environment = inventory["target_environment"]
    expected_environment = {
        "implementation_name": "cpython", "implementation_version": "3.12.15",
        "os_name": "posix", "platform_machine": "x86_64",
        "platform_python_implementation": "CPython", "platform_system": "Linux",
        "python_full_version": "3.12.15", "python_version": "3.12",
        "sys_platform": "linux", "extra": "",
    }
    if any(environment.get(key) != value for key, value in expected_environment.items()):
        raise ValueError("The declared dependency target changed")
    if materials["python_version"] != "3.12.15":
        raise ValueError("Unexpected target Python")
    packages, edges, total = {}, [], 0
    for record in records:
        data = read_regular(wheels / record["filename"], MAX_WHEEL_BYTES)
        if sha(data) != record["sha256"] or len(data) != record["size_bytes"]:
            raise ValueError("Wheel hash/size mismatch")
        name, version, build, tags = parse_wheel_filename(record["filename"])
        if (build or not all(tag.platform == "any" or tag.platform.endswith("_x86_64")
                             for tag in tags)):
            raise ValueError("Unexpected wheel target")
        # ZIP is inspected only; no members are extracted to the filesystem.
        import io
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            matches = [entry for entry in archive.infolist()
                       if entry.filename.endswith(".dist-info/METADATA")]
            if len(matches) != 1 or matches[0].file_size >= 1024**2:
                raise ValueError("Wheel metadata is absent or exceeds its bound")
            metadata_bytes = archive.read(matches[0])
        if sha(metadata_bytes) != record["metadata_sha256"]:
            raise ValueError("Wheel metadata identity differs")
        metadata = BytesParser().parsebytes(metadata_bytes)
        if (canonicalize_name(metadata["Name"]) != name or metadata["Version"] != str(version)
                or name in packages or name != record["name"] or str(version) != record["version"]):
            raise ValueError("Wheel package identity differs")
        if metadata["Requires-Python"] and Version("3.12.15") not in SpecifierSet(metadata["Requires-Python"]):
            raise ValueError("Target Python is unsupported by a wheel")
        packages[name] = str(version)
        total += len(data)
        if (metadata.get_all("Requires-Dist") or []) != record["requires_dist"]:
            raise ValueError("Declared wheel dependencies changed")
        for text in metadata.get_all("Requires-Dist") or []:
            requirement = Requirement(text)
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            if requirement.url or requirement.extras:
                raise ValueError("Active URL/extra dependencies are not in this fixed environment")
            edges.append({"package": name, "requirement": text,
                          "name": canonicalize_name(requirement.name),
                          "specifier": str(requirement.specifier)})
    if packages != materials["packages"] or total != inventory["total_wheel_bytes"]:
        raise ValueError("Complete package inventory or aggregate bytes differ")
    for edge in edges:
        if (edge["name"] not in packages
                or Version(packages[edge["name"]]) not in Requirement(edge["requirement"]).specifier):
            raise ValueError("Active Linux dependency is absent or incompatible")
    reachable = set(MANDATORY)
    while True:
        extended = reachable | {edge["name"] for edge in edges if edge["package"] in reachable}
        if extended == reachable:
            break
        reachable = extended
    if reachable != set(packages) or edges != inventory["active_dependency_edges"]:
        raise ValueError("The pinned graph is incomplete or includes unrelated packages")
    return {"wheel_files": len(records), "active_linux_dependency_edges": len(edges),
            "total_wheel_bytes": total, "target": "CPython3.12.15 Linux amd64",
            "wheel_import_install_or_execution": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheels", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = inspect(args.wheels)
    except (OSError, ValueError, KeyError, TypeError, zipfile.BadZipFile) as error:
        raise SystemExit(str(error)) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
