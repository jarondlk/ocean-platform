# Legacy Streamlit UI

This directory preserves the previous Streamlit application as reference
material. The active application is now the Next.js frontend in `frontend/`
backed by the FastAPI service in `api/`.

Use this archive for:

- Comparing historical Streamlit behavior against the current Next.js UI.
- Recovering implementation details that have not yet been ported.
- Thesis or project documentation screenshots that refer to the older UI.

Intentional local run from the repository root:

```bash
streamlit run archive/legacy-streamlit/app.py
```

Intentional container run from the repository root:

```bash
podman compose -f docker-compose.yml -f archive/legacy-streamlit/docker-compose.app.yml up -d --build
```

For normal development, use the root `docker-compose.next.yml` stack instead.

