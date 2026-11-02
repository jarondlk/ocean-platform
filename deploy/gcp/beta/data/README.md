# Existing local raw-data quarantine preparation

`prepare_quarantine.py` is a local-only packager. It does not upload, acquire,
normalize, register, publish, approve or seal scientific data. The selected user
scope is all eligible existing project data; this first package covers only the
available raw cohort listed in one exact historical manifest. Later cloud
ANEMONE/eDNA and historical-SST cohorts remain uninventoried and are not included.

The pinned manifest has SHA256
`9ac5170ff1030a9ffb153754865d5fd9bcd0acce81542456dae543e831b86a65`,
875,939 bytes, 1,860 source entries and 89,159,370 declared payload bytes. Its historical
absolute paths begin at `/Users/jaronchai/Desktop/source_chat_agt`. Current
checkout copies were independently reconciled against all 1,860 entry hashes. The
operator explicitly selects one complete source tree; the preparer maps that
exact historical prefix and never falls back to another location for a file.

The first actual plan refused duplicate paths before creating output: the old
manifest has only 1,849 unique paths. It repeats the Kraken TSV twice and the
2025-12-05 23:00 SST file eleven times. The available tree also contains one TXT
alias and ten other weekly SST paths omitted by that old path list; each has
exactly the corresponding pinned repeated entry's SHA256 and byte length.
`scope-amendment.json` explicitly lists those eleven relative paths, original
entry indices and byte pins. It preserves the original manifest, deduplicates
its paths and includes only these reviewed aliases, producing 1,860 unique raw
files and 89,159,370 bytes. This metadata correction asserts no scientific
equivalence, timestamp correction or new approval. Raw bytes are not modified. Byte-identical SST files under different date
filenames remain raw path aliases, not independent observations or validated
observation dates. Later normalization/publication must verify embedded
source-time provenance and scientific deduplication. This amendment does not
repair or establish scientific date/count semantics.

The amendment is pinned to SHA256
`73e49c36a7fa53d7cdb831970c57345a52250f8fffa582d62f6c8a7ebf2db1b3`
and must equal its Git HEAD blob before the CLI will prepare anything. Commit
the reviewed package first. The complete current raw-file inventory must match
the exact reconciled union; additional files are refused, never auto-added.

For a verified plan (no output directory created):

```sh
.venv/bin/python deploy/gcp/beta/data/prepare_quarantine.py \
  --source-root /Users/jaronchai/Documents/GitHub/provenance-eco-rag \
  --source-manifest /Users/jaronchai/Documents/GitHub/provenance-eco-rag/data/provenance/raw_source_manifest_latest.json \
  --output /private/tmp/ocean-beta-existing-raw-quarantine-20261102
```

Add exact `--prepare` to create the new private directory. The CLI accepts only
this checkout or the exact historical source tree and only the pinned manifest;
there are no checksum/count overrides. The output must be outside both trees,
have an existing nonsymlink parent, and not already exist. `/tmp` is a symlink on
this Mac, so use `/private/tmp`.

The archive is deterministic uncompressed USTAR with normalized ownership,
permissions and timestamp. It contains the exact original source manifest,
the pinned alias amendment, an explicit transfer manifest, and every reconciled
unique raw file under `payload/`.
The preparer checks each source's path, regular-file identity, length, hash and
before/after descriptor metadata, then rereads every archive member and verifies
complete membership and hashes before accepting `raw-quarantine.tar`. Failed
attempts retain `.partial` output and never return an accepted archive; inspect
them and choose a new output directory rather than blindly retrying.

Do not commit the archive or private source manifest to the repository. A later
separately scoped beta-quarantine upload must verify archive length/checksum and
private destination. This raw package is **not** a C09 snapshot/transfer receipt,
catalogue registration, normalization result, eligibility review or scientific
approval. Existing analysis/reliability outputs, serving embeddings, database
backups, operational manifests/logs, accounts/history and credentials are excluded.
