# Evidence archive

On 2026-11-26 the component-era evidence under `evidence/` (C01–C27) was
removed from the working tree to keep the repository readable. Nothing was
lost: every file is preserved byte-for-byte in commit
[`8f70cce`](https://github.com/jarondlk/ocean-platform/tree/8f70cceb3a1a279d484a54d703530706c1a8af35/docs/plans/ocean-v1/evidence),
which is part of `overhaul`'s history and is also tagged
`evidence/ocean-v1-2026-11-26`. History was not rewritten, so every commit ID
quoted by a receipt still resolves.

## What stayed

- All of `beta/` (the current B0–B5 phase).
- 249 files in `evidence/` that code, tests, CI or the C26 acceptance receipt
  read directly: frontend wire fixtures (C16, C18, C20, C21, C22), the C21
  export-contract check, C23 completion and retained cloud-session proof, C26
  start receipt and QA server, and the evidence scripts pinned by C26.
- Every planning document.

## Opening an archived file

Links in most documents now point to the archive commit on GitHub. Some
historical documents are pinned by hash in receipts and were left unchanged;
their relative links into `evidence/` no longer resolve locally. Open those with:

```bash
git show 8f70cce:docs/plans/ocean-v1/evidence/<path>
```

To restore the whole archive into a scratch folder:

```bash
git archive 8f70cce docs/plans/ocean-v1/evidence | tar -x -C /path/to/scratch
```

## Acceptance check

`scripts/run_system_acceptance.py` still verifies every original receipt. Files
present in the checkout are hashed from disk; archived files are checked against
the archive commit's Git objects, which gives the same byte-level guarantee.

## Going forward

`.gitignore` keeps raw output (`.bin`, `.stdout`, `.stderr`, `.sqlite3`, `.gz`,
`.log`, copied `source/` trees) under `docs/plans/` out of git. Commit small JSON
and Markdown receipts only, and keep raw logs in private storage.
