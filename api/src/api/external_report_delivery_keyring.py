"""Versioned keyring for durable external-report invitation delivery."""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass

DELIVERY_KEYRING_SCHEMA = "praviar.external-report-delivery-keyring.v1"
DEV_EXTERNAL_REPORT_DELIVERY_KEYRING_SECRET = (
    '{"schema_version":"praviar.external-report-delivery-keyring.v1",'
    '"active_key_id":"dev-v1","encryption_keys":'
    '{"dev-v1":"REREREREREREREREREREREREREREREREREREREREREQ"},'
    '"operation_hmac_key":"T09PT09PT09PT09PT09PT09PT09PT09PT09PT09PT08"}'
)
_KEY_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def _decode_key(value: object, *, field: str) -> bytes:
    if not isinstance(value, str) or re.fullmatch(r"[A-Za-z0-9_-]{43}", value) is None:
        raise ValueError(f"{field} must be a base64url key")
    try:
        decoded = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError) as exc:
        raise ValueError(f"{field} must be a base64url key") from exc
    if len(decoded) != 32:
        raise ValueError(f"{field} must decode to exactly 32 bytes")
    return decoded


@dataclass(frozen=True)
class ExternalReportDeliveryKeyRing:
    """Active encryption key plus retained decrypt-only rotation keys."""

    active_key_id: str
    encryption_keys: dict[str, bytes]
    operation_hmac_key: bytes

    @classmethod
    def from_secret(cls, secret: str) -> ExternalReportDeliveryKeyRing:
        try:
            payload = json.loads(secret)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ValueError("delivery keyring must be valid JSON") from exc
        if not isinstance(payload, dict) or set(payload) != {
            "schema_version",
            "active_key_id",
            "encryption_keys",
            "operation_hmac_key",
        }:
            raise ValueError("delivery keyring contains missing or unknown fields")
        if payload["schema_version"] != DELIVERY_KEYRING_SCHEMA:
            raise ValueError("delivery keyring schema_version is unsupported")
        active_key_id = payload["active_key_id"]
        raw_keys = payload["encryption_keys"]
        if not isinstance(active_key_id, str) or not _KEY_ID.fullmatch(active_key_id):
            raise ValueError("delivery keyring active_key_id is invalid")
        if not isinstance(raw_keys, dict) or not 1 <= len(raw_keys) <= 8:
            raise ValueError("delivery keyring must contain 1 to 8 encryption keys")
        encryption_keys: dict[str, bytes] = {}
        for key_id, raw_key in raw_keys.items():
            if not isinstance(key_id, str) or not _KEY_ID.fullmatch(key_id):
                raise ValueError("delivery keyring key id is invalid")
            encryption_keys[key_id] = _decode_key(raw_key, field=f"encryption_keys.{key_id}")
        if active_key_id not in encryption_keys:
            raise ValueError("delivery keyring active key is missing")
        return cls(
            active_key_id=active_key_id,
            encryption_keys=encryption_keys,
            operation_hmac_key=_decode_key(
                payload["operation_hmac_key"], field="operation_hmac_key"
            ),
        )

    @property
    def active_encryption_key(self) -> bytes:
        return self.encryption_keys[self.active_key_id]

    def encryption_key(self, key_id: str) -> bytes:
        try:
            return self.encryption_keys[key_id]
        except KeyError as exc:
            raise ValueError(f"delivery key id {key_id!r} is not retained") from exc
