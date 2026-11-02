# Source-only snapshot API overlay

This package pins the deployed catalogue API image and changes only the two
explicit host modules plus the new read-only GCS snapshot store module. It
preserves the other170 base source files, dependencies, migrations, entrypoint,
nonrootUID10001 and private loopback listener. The generated source manifest and
host configuration use the actual selected source commit; original172 base pins
and explicit supersessions remain traceable.

No dataset rows, scientific snapshots, activation documents, current access
decisions, dataset IDs, credentials or private keys enter the image or build
context. The only source configuration in the image is the exact nonsecret beta
bucket/prefix and opaque hash/object location of a separately selected private
activation document. That small source-binding file is root-owned0444 at
`/opt/ocean/beta-catalogue-source.json`. The actual activation stays in the beta
private snapshots bucket. A candidate without current hash-verified authority
must fail closed; it must not discover a source or silently fall back to empty.

The separate configuration renderer reads one explicitly selected private file
outside Git, verifies its exact hash and strict datasets-only metadata shape,
then emits only the opaque source binding to a new0600 file outside Git. It
does not approve data, copy activation contents, access GCS or upload anything.

After committing the exact selected modules/package sources:

```sh
.venv/bin/python deploy/gcp/beta/snapshot-api/checks.py
.venv/bin/python deploy/gcp/beta/snapshot-api/render_configuration.py \
  --activation /private/tmp/REVIEWED_PRIVATE_ACTIVATION.json \
  --activation-sha256 SELECTED_ACTIVATION_SHA256 \
  --output /private/tmp/NEW_SOURCE_BINDING.json
.venv/bin/python deploy/gcp/beta/snapshot-api/prepare_context.py \
  --revision FULL_SOURCE_COMMIT \
  --binding /private/tmp/NEW_SOURCE_BINDING.json \
  --binding-sha256 RENDERED_SOURCE_BINDING_SHA256 \
  --activation-sha256 SELECTED_ACTIVATION_SHA256 \
  --output /private/tmp/ocean-beta-snapshot-api-FULL_SOURCE_COMMIT
```

Context preparation performs no cloud operation, credential acquisition or data
read. It verifies committed source bytes, exact unchanged base files, explicit
binding/activation hashes and the complete static local import closure before
creating output. The operator must separately build an immutable image, upload
the selected private activation/snapshot bytes, and provide narrowly scoped GCS
read permissions. Mode `sealed-gcs-v1` changes only the catalogue source; research,
scientific approval, model and worker execution remain closed.
