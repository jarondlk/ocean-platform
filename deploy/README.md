# Deployment configuration

- `compose/` contains the optional local application and Ollama overlays plus
  the standalone production topology.
- `env/` contains production environment templates only. Keep populated
  production environment files in a secret-managed location.
- `gcp/` contains the managed Google Cloud prototype templates.

The root `compose.yml` remains the default local PostgreSQL service so
`podman compose up -d` continues to work. Combine it with
`deploy/compose/app.yml` to run FastAPI and Next.js locally.
