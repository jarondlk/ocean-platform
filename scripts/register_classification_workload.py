#!/usr/bin/env python3
"""Register the fixed Cloud Run identity used for classification application."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from sqlalchemy import or_, select


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from db.app_models import AppUser, AuditEvent
from db.connection import get_session


SERVICE_ACCOUNT_PATTERN = re.compile(
    r"^[a-z0-9][a-z0-9._-]{2,127}@[a-z0-9][a-z0-9.-]{4,126}"
    r"\.iam\.gserviceaccount\.com$"
)


def register_workload(session, subject: str) -> tuple[AppUser, bool]:
    subject = subject.strip().lower()
    if not SERVICE_ACCOUNT_PATTERN.fullmatch(subject):
        raise ValueError("Subject must be a Google service-account email")
    existing = session.scalar(
        select(AppUser).where(
            or_(
                AppUser.email == subject,
                (
                    (AppUser.auth_provider == "workload_identity")
                    & (AppUser.auth_subject == subject)
                ),
            )
        )
    )
    if existing is not None:
        if (
            existing.email != subject
            or existing.auth_provider != "workload_identity"
            or existing.auth_subject != subject
            or existing.role != "admin"
            or existing.account_type != "internal"
            or existing.status != "active"
        ):
            raise ValueError("A conflicting application user already exists")
        return existing, False
    user = AppUser(
        auth_provider="workload_identity",
        auth_subject=subject,
        email=subject,
        display_name="Cloud Run classification application",
        role="admin",
        account_type="internal",
        status="active",
    )
    session.add(user)
    session.flush()
    session.add(
        AuditEvent(
            action="system.classification_workload_registered",
            target_type="app_user",
            target_id=str(user.id),
            metadata_json={
                "auth_provider": "workload_identity",
                "auth_subject": subject,
                "role": "admin",
            },
        )
    )
    return user, True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--subject", required=True)
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Write the workload identity; otherwise print a plan.",
    )
    args = parser.parse_args()
    subject = args.subject.strip().lower()
    if not SERVICE_ACCOUNT_PATTERN.fullmatch(subject):
        parser.error("--subject must be a Google service-account email")
    if not args.execute:
        print(json.dumps({"execute": False, "subject": subject, "role": "admin"}))
        return 0
    with get_session() as session:
        user, created = register_workload(session, subject)
        result = {"execute": True, "user_id": str(user.id), "created": created}
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
