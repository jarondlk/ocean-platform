# Python dependency sets

The application keeps direct dependency inputs (`.in`) beside their
hash-verified, fully transitive locks (`.txt`).

| Set | Purpose |
| --- | --- |
| `runtime` | FastAPI, data processing, retrieval, and database runtime |
| `dev` | Runtime plus backend tests, coverage, and linting |
| `analysis` | Runtime plus publication-quality visualization tools |
| `archive` | Analysis tools plus the archived Streamlit application |

Install the development environment from the repository root with
`./scripts/bootstrap_dev.sh`.

Regenerate a lock from the repository root with Python 3.12 and `pip-tools`,
for all dependency sets:

```bash
for requirement_set in runtime dev analysis archive; do
  pip-compile \
    --generate-hashes \
    --strip-extras \
    --output-file "requirements/${requirement_set}.txt" \
    "requirements/${requirement_set}.in"
done
```

Regenerate all four locks after changing a shared input because the analysis
and archive sets inherit the runtime dependencies. Commit the `.in` and `.txt`
changes together and run `./scripts/bootstrap_dev.sh` before verification.
