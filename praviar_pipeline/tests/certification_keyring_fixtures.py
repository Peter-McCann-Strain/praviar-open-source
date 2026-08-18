"""Ephemeral report-certification keys for API and pipeline tests only."""

from __future__ import annotations

import base64
import json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from praviar_pipeline.checkpoint import CheckpointIntegrityKeyRing

TEST_REPORT_CERTIFICATION_KEY_ID = "test-report-v2"
TEST_CHECKPOINT_INTEGRITY_KEYS = CheckpointIntegrityKeyRing(
    active_key_id="test-checkpoint-v1",
    _keys={"test-checkpoint-v1": b"test-checkpoint-integrity-key-00001"},
)


def build_test_report_certification_keyrings(
    *, key_id: str = TEST_REPORT_CERTIFICATION_KEY_ID
) -> tuple[str, str]:
    """Return a fresh signing secret and its matching public verification ring."""
    private_key = Ed25519PrivateKey.generate()
    private_key_b64 = base64.b64encode(
        private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    ).decode()
    public_key_b64 = base64.b64encode(
        private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    ).decode()
    signing_keyring = json.dumps(
        {
            "schema_version": "praviar.report-certification-signing-keyring.v1",
            "active_key_id": key_id,
            "private_keys": {key_id: private_key_b64},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    public_keyring = json.dumps(
        {
            "schema_version": "praviar.report-certification-verification-keyring.v1",
            "keys": {key_id: public_key_b64},
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return signing_keyring, public_keyring


(
    TEST_REPORT_CERTIFICATION_SIGNING_KEYRING_SECRET,
    TEST_REPORT_CERTIFICATION_PUBLIC_KEYRING,
) = build_test_report_certification_keyrings()
