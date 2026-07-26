"""Generate a scrypt hash for the guarded development mock-login harness."""
from __future__ import annotations

import getpass
import hashlib
import secrets


def main() -> None:
    password = getpass.getpass("Mock account password: ")
    if len(password) < 12:
        raise SystemExit("Password must contain at least 12 characters.")
    if password != getpass.getpass("Confirm password: "):
        raise SystemExit("Passwords do not match.")

    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=16_384,
        r=8,
        p=1,
        dklen=64,
    )
    print(f"scrypt${salt.hex()}${derived.hex()}")


if __name__ == "__main__":
    main()
