"""Signed agency-bound pagination for immutable brief creation order."""

import base64
import hashlib
import hmac
import json
import uuid
from datetime import datetime

from backend.app.config import settings
from backend.app.errors import APIError


def signature(encoded):
    return hmac.new(settings.SESSION_CSRF_KEY.get_secret_value().encode(),
                    b"brief-list-v1:"+encoded.encode(), hashlib.sha256).hexdigest()


def encode_cursor(agency_id, stamp, identifier):
    payload = json.dumps([str(agency_id), stamp.isoformat(), str(identifier)], separators=(",", ":")).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    return encoded+"."+signature(encoded)


def decode_cursor(cursor, agency_id):
    try:
        encoded, supplied = cursor.split(".")
        if not hmac.compare_digest(supplied.encode(), signature(encoded).encode()):
            raise ValueError()
        values = json.loads(base64.b64decode(encoded+"="*(-len(encoded)%4), altchars=b"-_", validate=True))
        if not isinstance(values, list) or len(values) != 3 or uuid.UUID(values[0]) != agency_id:
            raise ValueError()
        stamp, identifier = datetime.fromisoformat(values[1]), uuid.UUID(values[2])
        if stamp.tzinfo is None:
            raise ValueError()
        return stamp, identifier
    except (ValueError, TypeError):
        raise APIError(400, "INVALID_REQUEST", "Pagination cursor is invalid for this workspace.") from None
