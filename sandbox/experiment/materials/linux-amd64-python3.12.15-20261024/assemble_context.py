"""Stage exact C23 build inputs, without downloading, installing or executing.

Requires a separately reviewed trusted-init source hash. Producing a context
does not verify the wrapper's behavior, build an image, or admit any execution.
Run with a new private output path; a failure retains partial work for inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat


MATERIALS = Path(__file__).resolve().parent
RECIPE = MATERIALS.parent.parent
MAX_WHEEL_BYTES = 128 * 1024**2
MAX_TOTAL_BYTES = 512 * 1024**2
SHA = re.compile(r"^[a-f0-9]{64}$")


def sha(value):
    return hashlib.sha256(value).hexdigest()


def stable(metadata):
    return (metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns,
            metadata.st_ctime_ns, metadata.st_mode, metadata.st_nlink)


def read_regular(path, maximum):
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > maximum:
        raise ValueError("Expected a bounded regular file without links")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        opened = os.fstat(fd)
        if (opened.st_dev, opened.st_ino, opened.st_size) != (
            before.st_dev, before.st_ino, before.st_size
        ):
            raise ValueError("Material changed while opening")
        with os.fdopen(fd, "rb", closefd=False) as source:
            data = source.read(maximum + 1)
        after = os.fstat(fd)
        final = path.lstat()
        if (len(data) != before.st_size or len(data) > maximum
                or stable(before) != stable(after) or stable(before) != stable(final)):
            raise ValueError("Material changed while reading")
        return data
    finally:
        os.close(fd)


def assemble(*, wheels, output, trusted_init, trusted_init_sha256):
    if not SHA.fullmatch(trusted_init_sha256):
        raise ValueError("An exact trusted-init source SHA256 is required")
    if output.exists() or output.is_symlink():
        raise ValueError("Output context must not already exist")
    if wheels.is_symlink() or not wheels.is_dir():
        raise ValueError("Wheel cache must be a real directory")
    manifest_bytes = read_regular(MATERIALS / "build-materials.json", 1024**2)
    manifest = json.loads(manifest_bytes)
    lock = read_regular(MATERIALS / "requirements.lock", 4 * 1024**2)
    if sha(lock) != manifest["lockfile_sha256"]:
        raise ValueError("Dedicated lock does not match its manifest")
    inventory = json.loads(read_regular(MATERIALS / "wheels.json", 4 * 1024**2))
    pins = json.loads(read_regular(MATERIALS / "recipe-inputs.json", 1024**2))
    records = inventory["wheels"]
    if not 7 <= len(records) <= 64:
        raise ValueError("Wheel set is outside the preparation bound")
    names = [record["filename"] for record in records]
    if len(set(names)) != len(names) or any(Path(name).name != name for name in names):
        raise ValueError("Wheel file names must be unique direct children")
    with os.scandir(wheels) as entries:
        actual = []
        for entry in entries:
            if len(actual) >= len(names):
                raise ValueError("Unexpected extra wheel-cache entry")
            actual.append(entry.name)
    if set(actual) != set(names):
        raise ValueError("Wheel cache does not contain the exact pinned set")
    if {r["name"]: r["version"] for r in records} != manifest["packages"]:
        raise ValueError("Wheel package identities differ from the complete manifest")
    expected_lock = "".join(r["name"] + "==" + r["version"] + " --hash=sha256:"
                            + r["sha256"] + "\n" for r in sorted(records, key=lambda r: r["name"]))
    if lock != expected_lock.encode():
        raise ValueError("Lock does not name exactly the selected wheel hashes")
    recipe_files = {}
    for name in ("Containerfile", ".containerignore", "verify_image.py"):
        data = read_regular(RECIPE / name, 1024**2)
        if sha(data) != pins["files"][name]:
            raise ValueError("Accepted preparation recipe was superseded; reconcile its pin first")
        recipe_files[name] = data
    execution_recipe = read_regular(MATERIALS / "Containerfile.execution", 1024**2)
    if sha(execution_recipe) != pins["execution_recipe_sha256"]:
        raise ValueError("Execution recipe differs from its material pin")
    wrapper = read_regular(trusted_init, 1024**2)
    if sha(wrapper) != trusted_init_sha256:
        raise ValueError("Trusted-init bytes do not match the supplied reviewed hash")
    # The accepted ignore file excludes everything by default. Add exactly this
    # one separately pinned trusted file to the private context's allowlist.
    context_files = {
        "Containerfile": execution_recipe,
        ".containerignore": recipe_files[".containerignore"] + b"!trusted_init.py\n",
        "verify_image.py": recipe_files["verify_image.py"],
        "build-materials.json": manifest_bytes,
        "requirements.lock": lock,
        "trusted_init.py": wrapper,
    }
    output.mkdir(mode=0o700)
    (output / "wheels").mkdir(mode=0o700)
    retained = {}
    for name, data in context_files.items():
        with (output / name).open("xb") as stream:
            stream.write(data)
        retained[name] = sha(data)
    total = 0
    for record in records:
        data = read_regular(wheels / record["filename"], MAX_WHEEL_BYTES)
        total += len(data)
        if (len(data) != record["size_bytes"] or sha(data) != record["sha256"]
                or total > MAX_TOTAL_BYTES):
            raise ValueError("Wheel size/hash/aggregate bound failed")
        with (output / "wheels" / record["filename"]).open("xb") as stream:
            stream.write(data)
        retained["wheels/" + record["filename"]] = record["sha256"]
    receipt = {
        "version": "c23-private-build-context-v1",
        "base_reference": manifest["base_reference"],
        "python_version": manifest["python_version"],
        "files": retained,
        "total_wheel_bytes": total,
        "image_built": False,
        "trusted_init_behavior_verified": False,
        "runtime_acceptance_verified": False,
        "dispatch_eligible": False,
    }
    with (output / "context-verification.json").open("x") as stream:
        json.dump(receipt, stream, indent=2, sort_keys=True)
        stream.write("\n")
    return receipt


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trusted-init", type=Path, required=True)
    parser.add_argument("--trusted-init-sha256", required=True)
    args = parser.parse_args()
    try:
        result = assemble(wheels=args.wheels, output=args.output, trusted_init=args.trusted_init,
                          trusted_init_sha256=args.trusted_init_sha256)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(str(error)) from None
    print(json.dumps({"context_files": len(result["files"]),
                      "total_wheel_bytes": result["total_wheel_bytes"],
                      "image_built": False, "dispatch_eligible": False}, sort_keys=True))


if __name__ == "__main__":
    main()
