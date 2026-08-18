from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import google_crc32c
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from api.services.epo_kms_keys import (
    EPCheckpointKMSKeyProvider,
    EPKMSKeyProvider,
    EPKMSKeyringConfig,
    EPKMSPublicKey,
    GoogleCloudKMSPublicKeyFetcher,
)

AUTHORITY_RAW = (
    Ed25519PrivateKey.from_private_bytes(b"\x41" * 32)
    .public_key()
    .public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
)
REGISTER_RAW = (
    Ed25519PrivateKey.from_private_bytes(b"\x42" * 32)
    .public_key()
    .public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
)


def _resource(name: str, version: int) -> str:
    return (
        "projects/praviar-prod/locations/europe-west2/keyRings/epo/"
        f"cryptoKeys/{name}/cryptoKeyVersions/{version}"
    )


def _keyring_json(*, purpose: str = "checkpoint") -> str:
    suffix = "checkpoint" if purpose == "checkpoint" else "acquisition"
    return json.dumps(
        {
            "schema_version": "praviar.epo-kms-public-keyring.v1",
            "keyset_purpose": purpose,
            "keys": [
                {
                    "key_id": f"epo-authority-{suffix}-v1",
                    "purpose": f"authority_{suffix}",
                    "kms_crypto_key_version": _resource(f"authority-{suffix}", 1),
                    "expected_public_key_sha256": hashlib.sha256(AUTHORITY_RAW).hexdigest(),
                    "expected_protection_level": "HSM",
                    "not_before": "2026-01-01T00:00:00Z",
                    "not_after": "2030-01-01T00:00:00Z",
                    "status": "active",
                    "revocation_epoch": 0,
                    "revoked_at": None,
                },
                {
                    "key_id": f"epo-register-{suffix}-v1",
                    "purpose": f"register_{suffix}",
                    "kms_crypto_key_version": _resource(f"register-{suffix}", 1),
                    "expected_public_key_sha256": hashlib.sha256(REGISTER_RAW).hexdigest(),
                    "expected_protection_level": "HSM",
                    "not_before": "2026-01-01T00:00:00Z",
                    "not_after": "2030-01-01T00:00:00Z",
                    "status": "active",
                    "revocation_epoch": 0,
                    "revoked_at": None,
                },
            ],
        }
    )


class _Fetcher:
    def __init__(self) -> None:
        self.calls = 0

    async def fetch(self, resource_name: str) -> EPKMSPublicKey:
        self.calls += 1
        raw = AUTHORITY_RAW if "authority-" in resource_name else REGISTER_RAW
        return EPKMSPublicKey(
            resource_name=resource_name,
            raw_public_key=raw,
            algorithm="EC_SIGN_ED25519",
            protection_level="HSM",
        )


@pytest.mark.asyncio
async def test_kms_provider_pins_versions_fingerprints_and_caches_public_keys() -> None:
    config = EPKMSKeyringConfig.from_json(
        _keyring_json(),
        expected_keyset_purpose="checkpoint",
    )
    fetcher = _Fetcher()
    provider = EPCheckpointKMSKeyProvider(config, fetcher=fetcher)

    first = await provider.load_trusted_checkpoint_keys()
    second = await provider.load_trusted_checkpoint_keys()

    assert set(first) == {"epo-authority-checkpoint-v1", "epo-register-checkpoint-v1"}
    assert first == second
    assert fetcher.calls == 2


@pytest.mark.asyncio
async def test_kms_provider_fails_closed_on_fingerprint_or_protection_drift() -> None:
    raw = json.loads(_keyring_json())
    raw["keys"][0]["expected_public_key_sha256"] = "f" * 64
    config = EPKMSKeyringConfig.model_validate(raw)
    with pytest.raises(ValueError, match="governed fingerprint"):
        await EPKMSKeyProvider(config, fetcher=_Fetcher()).load_trusted_keys()

    raw = json.loads(_keyring_json())
    raw["keys"][0]["expected_protection_level"] = "SOFTWARE"
    config = EPKMSKeyringConfig.model_validate(raw)
    with pytest.raises(ValueError, match="protection level"):
        await EPKMSKeyProvider(config, fetcher=_Fetcher()).load_trusted_keys()


def test_kms_keyring_rejects_absence_purpose_confusion_and_duplicate_material() -> None:
    with pytest.raises(ValueError, match="absent"):
        EPKMSKeyringConfig.from_json("", expected_keyset_purpose="checkpoint")
    with pytest.raises(ValueError, match="wrong trust boundary"):
        EPKMSKeyringConfig.from_json(
            _keyring_json(purpose="acquisition"),
            expected_keyset_purpose="checkpoint",
        )

    raw = json.loads(_keyring_json())
    raw["keys"][1]["expected_public_key_sha256"] = raw["keys"][0]["expected_public_key_sha256"]
    with pytest.raises(ValueError, match="purpose-distinct"):
        EPKMSKeyringConfig.model_validate(raw)


class _Response:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _Session:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.closed = False
        self.request = SimpleNamespace(url="", timeout=0.0)

    def get(self, url: str, *, timeout: float) -> _Response:
        self.request.url = url
        self.request.timeout = timeout
        return _Response(self._payload)

    def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_google_kms_fetcher_verifies_crc_subject_algorithm_and_ed25519_pem() -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(b"\x43" * 32)
    pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    resource = _resource("authority-checkpoint", 3)
    session = _Session(
        {
            "name": resource,
            "algorithm": "EC_SIGN_ED25519",
            "protectionLevel": "HSM",
            "pem": pem,
            "pemCrc32c": str(google_crc32c.value(pem.encode("utf-8"))),
        }
    )
    fetcher = GoogleCloudKMSPublicKeyFetcher(
        session_factory=lambda: session,
        timeout_seconds=2.5,
    )

    result = await fetcher.fetch(resource)

    assert result.resource_name == resource
    assert result.protection_level == "HSM"
    assert session.closed is True
    assert session.request.timeout == 2.5
    assert session.request.url.endswith(f"/{resource}/publicKey")


@pytest.mark.asyncio
async def test_google_kms_fetcher_rejects_crc_mismatch() -> None:
    private_key = Ed25519PrivateKey.from_private_bytes(b"\x44" * 32)
    pem = (
        private_key.public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("ascii")
    )
    resource = _resource("register-checkpoint", 4)
    session = _Session(
        {
            "name": resource,
            "algorithm": "EC_SIGN_ED25519",
            "protectionLevel": "HSM",
            "pem": pem,
            "pemCrc32c": "0",
        }
    )

    with pytest.raises(ValueError, match="CRC32C"):
        await GoogleCloudKMSPublicKeyFetcher(session_factory=lambda: session).fetch(resource)
