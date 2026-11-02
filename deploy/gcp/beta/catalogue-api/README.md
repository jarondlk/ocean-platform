# Explicit empty beta catalogue API

This source-only overlay connects actual catalogue discovery to an authoritative
empty beta registry. It includes no datasets, fixtures, credentials, source
discovery, scientific approvals, migrations, or background execution. Nonempty
registry configuration requires a separate reviewed sealed-data integration.

The immutable serving API base remains pinned. The package replaces only
`api/v1_host.py`, adds `api/v1_catalogue_host.py`, and regenerates the API source
manifest and host configuration against the selected source commit. The
171-source original manifest is retained as package input; its reviewed digest
and every corresponding original Git object are verified. The other170 base
sources, dependency lock, entrypoint and migration files must remain unchanged.
The static API import closure must be present in the base or explicit overlay.

After committing the exact source, prepare a new context:

```sh
.venv/bin/python deploy/gcp/beta/catalogue-api/prepare_context.py \
  --revision FULL_SOURCE_COMMIT \
  --output /private/tmp/ocean-beta-catalogue-api-FULL_SOURCE_COMMIT
```

Preparation performs no cloud operation. The operator separately builds an
immutable image and selects it for the same beta service. Set
`ENABLE_V1_CATALOGUE=true` and `ENABLE_V1_CATALOGUE_BROWSER=true` only for that
configured candidate; keep research, experiment and dispatch flags closed.
The Dockerfile inherits the original nonroot user, entrypoint, loopback listener
and dependency installation. All replaced files are root-owned regular0444.

Run the14 offline packaging boundary probes independently:

```sh
.venv/bin/python deploy/gcp/beta/catalogue-api/checks.py
```

These reject unauthorized registry contents, foreign targets, altered base pins,
image/entrypoint/build-instruction changes and path escape. They also verify the
current static import closure fits the pinned base plus explicit module overlay.
The full preparer additionally verifies exact committed checkout bytes and only
creates the context after every source check succeeds.
