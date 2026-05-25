#!/usr/bin/env python3
"""
Generate ADMIN_PASSWORD_HASH for the control center.

Usage:
    python scripts/gen_admin_hash.py

Enter your password when prompted. Copy the output and set it as
ADMIN_PASSWORD_HASH in Render environment variables.
"""
import binascii
import getpass
import hashlib
import secrets


def main() -> None:
    password = getpass.getpass("Enter admin password: ")
    if not password:
        print("Error: password cannot be empty")
        return
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 260_000)
    result = f"{salt}:{binascii.hexlify(h).decode()}"
    print("\nSet this as ADMIN_PASSWORD_HASH in Render env vars:\n")
    print(result)
    print()


if __name__ == "__main__":
    main()
