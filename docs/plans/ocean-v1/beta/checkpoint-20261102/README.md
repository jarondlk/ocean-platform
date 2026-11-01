# Beta host source overlay — 2026-11-02 JST

This additive audit qualifies the independently configured authenticated host/API
checkpoint against C27's accepted predecessor. It does not rerun application
tests, accept a live deployment, or retarget any original receipt.

```sh
.venv/bin/python docs/plans/ocean-v1/beta/checkpoint-20261102/verify.py
```

The read-only verifier checks the actual working bytes:

- 841 of the original 844 accepted runtime/configuration paths are unchanged.
- Three intentional supersessions record their predecessor and replacement
  hashes: the added authenticated-host CI job, optional RuntimeApp fetcher, and
  separate TypeScript hosting exclusion.
- 36 additive host/API source paths are pinned, including the host `lib` helpers
  and `.gitignore` override. None is ignored by Git. Generated build/dependency
  directories are excluded.
- All 5,368 predecessor evidence files, 90 C27 package artifacts and 42 protected
  unrelated/scientific paths retain their original bytes.

The composed 880-path source identity is
`sha256:1d3b93f3abbf914d165982a43d4a24f830d975712029e7e5570cb0b868828128`.
The source and preservation manifests remain a checkpoint audit. The new source
requires a separate source-bound hosted CI delivery receipt; none is claimed
here. Runtime packaging, OAuth/provider enrollment, cloud IAM/network/session
acceptance and actual deployment remain separate work. Original C26/C27 gates
and P2 D26-07 are not cleared by this audit.
