#!/usr/bin/env python3
"""Render non-secret Cloud Run templates without contacting GCP."""
from __future__ import annotations

import argparse
import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_DIR = PROJECT_ROOT / "deploy" / "gcp"
TEMPLATES = (
    "service.template.yaml",
    "job-migrate.template.yaml",
    "job-pipeline.template.yaml",
    "job-embedding.template.yaml",
    "job-evaluation.template.yaml",
)
TOKEN_PATTERN = re.compile(
    r"\b(?:PROJECT_ID|PROJECT_NUMBER|REGION|ARTIFACT_REPOSITORY|IMAGE_TAG|"
    r"CLOUD_SQL_INSTANCE|PUBLIC_APP_URL|OIDC_PROVIDER_ID_VALUE|"
    r"OIDC_PROVIDER_NAME_VALUE|OIDC_ISSUER_VALUE|OIDC_CLIENT_ID_VALUE|"
    r"OLLAMA_PRIVATE_URL|DATA_BUCKET)\b"
)


def render_templates(values: dict[str, str], output_dir: Path) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered_paths: list[Path] = []
    for template_name in TEMPLATES:
        source = TEMPLATE_DIR / template_name
        rendered = source.read_text(encoding="utf-8")
        for token, value in values.items():
            rendered = rendered.replace(token, value)
        unresolved = sorted(set(TOKEN_PATTERN.findall(rendered)))
        if unresolved:
            raise ValueError(
                f"{template_name} has unresolved values: {', '.join(unresolved)}"
            )
        destination = output_dir / template_name.replace(
            ".template.yaml",
            ".rendered.yaml",
        )
        destination.write_text(rendered, encoding="utf-8")
        rendered_paths.append(destination)
    return rendered_paths


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-id", default="data-infra-infobio")
    parser.add_argument("--project-number", default="469489188516")
    parser.add_argument("--region", default="asia-northeast1")
    parser.add_argument("--repository", default="ocean-platform")
    parser.add_argument("--image-tag", required=True)
    parser.add_argument("--cloud-sql-instance", default="ocean-postgres")
    parser.add_argument("--public-app-url", required=True)
    parser.add_argument("--data-bucket", required=True)
    parser.add_argument("--oidc-provider-id", default="google")
    parser.add_argument("--oidc-provider-name", default="Google")
    parser.add_argument("--oidc-issuer", default="https://accounts.google.com")
    parser.add_argument("--oidc-client-id", required=True)
    parser.add_argument("--ollama-private-url", required=True)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=TEMPLATE_DIR,
    )
    args = parser.parse_args()
    required_values = {
        "image-tag": args.image_tag,
        "public-app-url": args.public_app_url,
        "data-bucket": args.data_bucket,
        "oidc-client-id": args.oidc_client_id,
        "ollama-private-url": args.ollama_private_url,
    }
    for option, value in required_values.items():
        if not value.strip():
            parser.error(f"--{option} must not be blank")
    values = {
        "PROJECT_ID": args.project_id,
        "PROJECT_NUMBER": args.project_number,
        "REGION": args.region,
        "ARTIFACT_REPOSITORY": args.repository,
        "IMAGE_TAG": args.image_tag,
        "CLOUD_SQL_INSTANCE": args.cloud_sql_instance,
        "PUBLIC_APP_URL": args.public_app_url.rstrip("/"),
        "OIDC_PROVIDER_ID_VALUE": args.oidc_provider_id,
        "OIDC_PROVIDER_NAME_VALUE": args.oidc_provider_name,
        "OIDC_ISSUER_VALUE": args.oidc_issuer.rstrip("/"),
        "OIDC_CLIENT_ID_VALUE": args.oidc_client_id,
        "OLLAMA_PRIVATE_URL": args.ollama_private_url.rstrip("/"),
        "DATA_BUCKET": args.data_bucket,
    }
    for path in render_templates(values, args.output_dir):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
