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
for example:

```bash
pip-compile \
  --generate-hashes \
  --output-file requirements/dev.txt \
  requirements/dev.in
```
