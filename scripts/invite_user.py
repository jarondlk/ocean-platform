#!/usr/bin/env python3
"""Create or renew an invite without requiring an existing administrator.

This is the bootstrap path for the first admin account:

    python scripts/invite_user.py admin@example.org --role admin --account-type internal
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from api.auth import VALID_ACCOUNT_TYPES, VALID_ROLES, normalize_email
from db.app_models import AppUser, AuditEvent, UserInvitation
from db.connection import get_session


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an invite-only account")
    parser.add_argument("email")
    parser.add_argument("--role", choices=sorted(VALID_ROLES), default="viewer")
    parser.add_argument(
        "--account-type",
        choices=sorted(VALID_ACCOUNT_TYPES),
        default="research",
    )
    parser.add_argument("--expires-in-days", type=int, default=7)
    args = parser.parse_args()

    if not 1 <= args.expires_in_days <= 90:
        raise SystemExit("--expires-in-days must be between 1 and 90")
    email = normalize_email(args.email)
    expires_at = datetime.now(timezone.utc) + timedelta(days=args.expires_in_days)

    with get_session() as session:
        if session.scalar(select(AppUser).where(AppUser.email == email)):
            raise SystemExit(f"A user already exists for {email}")
        invitation = session.scalar(
            select(UserInvitation).where(UserInvitation.email == email)
        )
        if invitation is not None and invitation.status == "accepted":
            raise SystemExit(f"The invitation for {email} was already accepted")
        if invitation is None:
            invitation = UserInvitation(email=email)
            session.add(invitation)
        invitation.role = args.role
        invitation.account_type = args.account_type
        invitation.status = "pending"
        invitation.expires_at = expires_at
        invitation.accepted_at = None
        session.flush()
        session.add(
            AuditEvent(
                action="system.invitation_created",
                target_type="invitation",
                target_id=str(invitation.id),
                metadata_json={
                    "email": email,
                    "role": args.role,
                    "account_type": args.account_type,
                },
            )
        )

    print(
        f"Invited {email} as {args.role}/{args.account_type}; "
        f"expires {expires_at.isoformat()}"
    )


if __name__ == "__main__":
    main()
