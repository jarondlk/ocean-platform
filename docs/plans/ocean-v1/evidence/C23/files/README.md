# C23 file-boundary checkpoint

This is local synthetic staging/output validation. No stored Python, container,
VM, gVisor, cloud, real experiment or scientific result was executed. These
checks cannot prove containment, resource enforcement or whole-job termination.
The supervisor must establish termination before collecting output bytes and
must independently recheck current admission before retaining a usable result.

## Interfaces and fixed profiles

`stage_inputs(parent, envelope)` takes an existing private owner directory and
an exact `VerifiedEnvelope`. It creates `parent/<job_id>/inputs/analysis.py`,
`manifest.json` and the exact original frozen input files. Exported names cannot
collide with the two reserved names. Code, manifest and inputs jointly count
toward the proposal input limit. Source code is copied without interpretation.
The actual approved C22/fake-dispatch fixture includes an inert file-writing
sentinel; it never appears.

Paths are opened component by component with no-follow directory FDs. Files are
create-only, fsynced, owner-readable (0400); the input directory is 0500. Reuse
requires the exact readonly filenames, bytes and hashes. Partial/tampered stages
are refused, never overwritten or automatically deleted. The private job root
stays 0700 for trusted future preparation. Only private non-symlink sibling
directories named `rootfs`, `outputs`, `scratch` may coexist with `inputs`.
`verify_staged_inputs` rereads these pins immediately before a future create.
Actual runtime UID mapping/readability remains an unverified Linux gate; no
permission broadening is performed here.

`validate_expected_outputs` rejects unsupported declarations before launch.
`validate_outputs` requires an already stopped writer and accepts exact declared
names only. It rejects symlinks, hardlinks, nonregular files, FIFO/device/socket
files, directories, missing/extra names and unstable file/directory identity.
Reads are bounded, nonblocking and checked against FD/name metadata. Directory
enumeration stops at the expected maximum plus one before a whole untrusted
listing can allocate memory. Input/root/output enumerations all use that bound.

Supported profiles:

- JSON: a UTF-8 object with exactly `columns` and `rows`; unique nonempty string
  columns and rectangular rows of finite primitive cells. Limits are 128 columns,
  100,000 rows, 1,000,000 cells and 16,384 bytes per string token/cell. Nesting and
  structural counts are checked before JSON allocation. Duplicate keys, NaN,
  infinity and nested cells are refused. Exact original machine bytes, int64,
  Unicode, null and numeric negatives are retained.
- CSV: strict UTF-8 rectangular records, distinct headers, quoted-field grammar,
  LF or CRLF (quoted newlines permitted), with the same row/column/cell limits.
  Machine strings are retained unchanged. Formula-safe human CSV remains a
  separate C07 presentation operation; no download/UI endpoint is added.
- PNG: strict noninterlaced 8-bit grayscale, RGB or RGBA; maximum dimension4096
  and total pixels4,194,304. Chunk CRC/order, exact bounded zlib scanline bytes
  and filter values are checked. Ancillary chunks, text/profiles, animations,
  palettes and broader raster formats are deliberately unsupported. Typical
  plotting-library PNGs containing metadata may require a future reviewed writer
  or broader profile; this validator never silently strips bytes.

Outputs, captured stdout/stderr (at most1MiB each) and the final manifest jointly
count toward `min(proposal_limit, 50MiB)`. The immutable result exposes exact
file/log bytes and a detached manifest. Experimental/unverified-science labels
persist. Log completeness is explicitly `not_asserted`; a caller cannot infer
that a bounded capture was complete. Scientific conclusions are not validated.

## Evidence

`initial-observed-result.json` honestly records the initial93 terminal passes
before the directory-listing review amendment; no original source-before map
was captured and none is invented.

`focused-01` preserves a failed dotted-module coverage startup attempt plus
clean Ruff on that earlier source, with source-before/after pins. NumPy failed
to load before test collection; this is not a waived passing test result.

`focused-02-observed` stores the actual later95-pass terminal output and clean
Ruff after the bounded-directory amendment. Filesystem-based coverage succeeds:
93.23% for this module. Its source snapshot was taken after execution, explicitly
qualified; root's combined source-pinned acceptance must bind final source.
No additional reruns were requested after that result. Original evidence is
create-only and retained. No broad suites, source commits or pushes were made
by this delegate.
