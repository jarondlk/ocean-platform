# Security Policy

## Reporting a Vulnerability

Do not open a public issue for a suspected vulnerability or include secrets,
tokens, private datasets, or exploit details in public discussion.

Use the repository's private GitHub security-advisory reporting flow when it is
available. If private reporting is unavailable, contact the maintainers through
an established private project channel and include:

- the affected commit or version;
- the vulnerable route or component;
- the minimum steps needed to reproduce the issue;
- the expected and observed security boundary;
- whether any credentials or real data may have been exposed.

The maintainers should acknowledge a report privately, assess its severity,
prepare a fix without disclosing exploit details, rotate affected credentials,
and publish an advisory after users have a safe upgrade path.

## Supported Version

This repository is an active MVP. Security fixes are made on the current default
branch; older commits and the archived Streamlit application are not maintained
as supported releases.

## Security Documentation

The application threat model and authorization matrix are in
[`docs/SECURITY.md`](docs/SECURITY.md). Production configuration, secret
handling, TLS, backup, and rollback requirements are in
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).
