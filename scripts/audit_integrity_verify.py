"""Verify the append-only access-decision integrity chain."""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "apps", "api"))

from app.db.session import SessionLocal
from app.security.audit_integrity import verify_audit_chain

with SessionLocal() as session:
    result = verify_audit_chain(session)
print(json.dumps(result.model_dump(mode="json"), sort_keys=True))
# This is a required security gate: legacy evidence is reported explicitly
# and must not be treated as a successful verification.
raise SystemExit(0 if result.status == "verified" else 1)
