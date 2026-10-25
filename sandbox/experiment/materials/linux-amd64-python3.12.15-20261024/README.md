# Pinned C23 Linux amd64 scientific build materials

Prepared from official Docker Registry and PyPI metadata on 2026-10-24 JST.
These are real downloaded material pins. No scientific image has been built,
no wheel has been installed/imported, and no runtime acceptance is claimed.
The trusted-init implementation must be separately frozen and reviewed before
building the execution image. Preparation does not grant dispatch eligibility.

The base is Docker Official Image `python:3.12.15-slim-bookworm`, selected for
Linux amd64 by its platform manifest, not the moving tag or multi-platform index:

`docker.io/library/python@sha256:57d96f71de145a98e7ceca18ee4ade77bba4103a33a72dfaea026b23625c6bf0`

Registry manifest/config bytes match their SHA256 identities; the config declares
Python3.12.15 and amd64. This is registry metadata verification, not an observation
of a running image or verification of all materialized filesystem contents.
[Official image](https://hub.docker.com/_/python)

The complete lock has 22 packages and 30 active Linux dependency edges. The
mandatory scientific packages are NumPy2.5.4, Pandas3.1.0, PyArrow26.0.0,
SciPy1.18.1, statsmodels0.15.0, Matplotlib3.11.2 and packaging26.3.
`wheels.json` records every transitive version, selected filename/size/SHA256,
wheel-metadata hash, official release-file record and Linux dependency graph.
All156205254 downloaded bytes match official PyPI release hashes and sizes.
No sdist, editable source or optional extras are part of the environment.

## Download the exact binary wheel set

Use a trusted preparation interpreter. This downloads files only; it does not
install or import them. The initial resolver used binary-only cross-platform
download; replay the frozen lock with dependency resolution disabled:

```sh
.venv/bin/python -m pip --isolated download \
  --index-url https://pypi.org/simple \
  --only-binary=:all: --no-deps --require-hashes \
  --python-version 3.12.15 --implementation cp \
  --abi cp312 --abi abi3 --abi none \
  --platform manylinux_2_28_x86_64 \
  --platform manylinux_2_17_x86_64 \
  --platform manylinux_2_5_x86_64 \
  --requirement sandbox/experiment/materials/linux-amd64-python3.12.15-20261024/requirements.lock \
  --dest /private/tmp/c23-pinned-wheelhouse
```

Cross-platform resolution is preparation. `verify_wheelhouse.py` independently
checks the bytes, metadata, complete version inventory, active dependency markers
for Linux CPython3.12.15 and reachability from the seven mandatory packages.
It uses `packaging` from its trusted tool interpreter, never from a downloaded
wheel. Later image installation must still pass `verify_image.py --verify-installed`.
[pip cross-platform download](https://pip.pypa.io/en/stable/cli/pip_download/)

## Assemble a private offline build context

`assemble_context.py` requires a real reviewed `trusted_init.py` and its exact
64-hex source hash. It pins the accepted preparation recipe, extends it only
with the trusted-init COPY to `/opt/c23/trusted_init.py` (root-owned0444), and
adds that one file to the context ignore allowlist. It verifies/copies exactly
the22 selected wheels, lock, strict material manifest and fixed helper. It
refuses existing contexts, linked/nonregular files, changed bytes or extra/missing
wheel files. It performs no downloads, installation, builds or execution.

From the repository root, replace `REVIEWED_64_HEX_SHA256` with the actual frozen
source pin; the literal placeholder is rejected:

```sh
.venv/bin/python sandbox/experiment/materials/linux-amd64-python3.12.15-20261024/verify_wheelhouse.py \
  --wheels /private/tmp/c23-pinned-wheelhouse
.venv/bin/python sandbox/experiment/materials/linux-amd64-python3.12.15-20261024/assemble_context.py \
  --wheels /private/tmp/c23-pinned-wheelhouse \
  --output /private/tmp/c23-reviewed-build-context \
  --trusted-init sandbox/experiment/trusted_init.py \
  --trusted-init-sha256 REVIEWED_64_HEX_SHA256
```

After wrapper review, preload and verify the pinned base through an authorized
trusted preparation step. Build the private context using Podman with
`--pull=never --network=none` and the exact `SCIENTIFIC_BASE` reference above.
Record the actual command, architecture, image/config/layer digests, installed
Python/packages, wrapper hash and materialized immutable rootfs before admission.
The execution recipe adds no application, database or cloud credentials.

The156MB wheel cache and a deliberately inert context-assembly fixture are in
`/private/tmp/ocean-c23-material-discovery-20261024` on the preparation Mac.
The `assembly-fixture-NOT-FOR-BUILD` context contains a comment-only stand-in
wrapper and **must never be built or executed**. Its receipt is only a helper
test. Binary wheels/cache are not tracked in Git and may need reacquisition.

Evidence is in `docs/plans/ocean-v1/evidence/C23/materials/discovery-20261024`.
Eight preparation checks pass; this clears material preparation only. Real
image build, installed-image graph verification, trusted-init behavior, runtime
containment/resource/termination/output extraction and numerical fixtures remain
separate mandatory C23 gates. Original preparation files and receipts are unchanged.
