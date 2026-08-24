# Legacy Streamlit UI

This directory preserves the previous Streamlit application as reference
material. The active application is now the Next.js frontend in `frontend/`
backed by the FastAPI service in `api/`.

Status as of **2026-07-21**: this archive is not the source of truth for the
current prototype. Use the root `README.md` for current screenshots and public
status, `handoff.md` for resume context, and `docs/ROADMAP.md` for planned
engineering work.

Use this archive for:

- Comparing historical Streamlit behavior against the current Next.js UI.
- Recovering implementation details if a remaining parity question comes up.
- Thesis or project documentation screenshots that refer to the older UI.

Intentional local run from the repository root:

```bash
streamlit run archive/legacy-streamlit/app.py
```

Intentional container run from the repository root:

```bash
podman compose -f compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build
```

For normal development, combine the root `compose.yml` with
`deploy/compose/app.yml` instead.
