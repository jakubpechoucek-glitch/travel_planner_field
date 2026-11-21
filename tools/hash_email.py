"""Print the key hash of an e-mail address (for BOOTSTRAP_ADMIN_HASHES).

Usage:  IDENTITY_KEY=... python tools/hash_email.py
The e-mail is typed at a hidden prompt so it does not end up in shell history.
"""

import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from travel_planner.identity import key_hash  # noqa: E402

secret = os.environ.get("IDENTITY_KEY")
if not secret:
    sys.exit("Set IDENTITY_KEY first (the same secret the app uses).")
print(key_hash(getpass.getpass("Sign-in e-mail: "), secret))
