"""KMS-backed trust-key loading for EPO acquisition and checkpoint receipts.

Only public keys are exposed to the worker. Private signing capability remains
inside the collector's Cloud KMS boundary. Every configured key is pinned to an
immutable CryptoKeyVersion and to the expected raw Ed25519 public-key digest.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from importlib import import_module
from typing import Any, Literal, Protocol
from urllib.parse import quote

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from praviar_pipeline.models.epo_publication import EPTrustedAcquisitionKey
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
_KMS_API_ROOT = "https://cloudkms.googleapis.com/v1"
_KMS_VERSION_PATTERN = (
    r"^projects/[a-z][a-z0-9-]{4,28}[a-z0-9]/locations/[a-z0-9-]{1,63}/"
    r"keyRings/[A-Za-z0-9_-]{1,63}/cryptoKeys/[A-Za-z0-9_-]{1,63}/"
    r"cryptoKeyVersions/[1-9][0-9]*$"
)

EPTrustPurpose = Literal[
    "authority_acquisition",
    "register_acquisition",
    "authority_checkpoint",
    "register_checkpoint",
]


@dataclass(frozen=True, slots=True)
class EPKMSPublicKey:
    """Integrity-checked public-key response from one immutable KMS version."""

    resource_name: str
    raw_public_key: bytes
    algorithm: str
    protection_level: str


class EPKMSPublicKeyFetcher(Protocol):
    """Narrow external boundary used by the keyring provider."""

    async def fetch(self, resource_name: str) -> EPKMSPublicKey: ...


class EPKMSKeyDescriptor(BaseModel):
    """Governance metadata for one trusted KMS key version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key_id: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]{2,63}$")
    purpose: EPTrustPurpose
    kms_crypto_key_version: str = Field(pattern=_KMS_VERSION_PATTERN)
    expected_public_key_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    expected_protection_level: Literal["SOFTWARE", "HSM", "EXTERNAL", "EXTERNAL_VPC"]
    not_before: datetime
    not_after: datetime
    status: Literal["active", "revoked"]
    revocation_epoch: int = Field(ge=0)
    revoked_at: datetime | None = None

    @model_validator(mode="after")
    def _validate_as_trusted_key(self) -> EPKMSKeyDescriptor:
        # Reuse the evidence model's timezone, ordering, and revocation rules.
        EPTrustedAcquisitionKey(
            key_id=self.key_id,
            public_key=b"\0" * 32,
            purpose=self.purpose,
            not_before=self.not_before,
            not_after=self.not_after,
            status=self.status,
            revocation_epoch=self.revocation_epoch,
            revoked_at=self.revoked_at,
        )
        return self


class EPKMSKeyringConfig(BaseModel):
    """Strict, rotation-aware KMS public-key contract delivered as one secret."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["praviar.epo-kms-public-keyring.v1"]
    keyset_purpose: Literal["acquisition", "checkpoint"]
    keys: tuple[EPKMSKeyDescriptor, ...] = Field(min_length=2, max_length=16)

    @model_validator(mode="after")
    def _validate_keyset(self) -> EPKMSKeyringConfig:
        expected_purposes: set[str]
        if self.keyset_purpose == "acquisition":
            expected_purposes = {"authority_acquisition", "register_acquisition"}
        else:
            expected_purposes = {"authority_checkpoint", "register_checkpoint"}
        if any(key.purpose not in expected_purposes for key in self.keys):
            raise ValueError("KMS keyring contains a purpose from another trust boundary")
        active_purposes = {key.purpose for key in self.keys if key.status == "active"}
        if active_purposes != expected_purposes:
            raise ValueError("KMS keyring requires an active authority and Register key")
        if len({key.key_id for key in self.keys}) != len(self.keys):
            raise ValueError("KMS key ids must be unique")
        if len({key.kms_crypto_key_version for key in self.keys}) != len(self.keys):
            raise ValueError("KMS CryptoKeyVersions must be unique")
        if len({key.expected_public_key_sha256 for key in self.keys}) != len(self.keys):
            raise ValueError("KMS public-key material must be purpose-distinct")
        return self

    @classmethod
    def from_json(
        cls,
        raw: str,
        *,
        expected_keyset_purpose: Literal["acquisition", "checkpoint"],
    ) -> EPKMSKeyringConfig:
        if not raw.strip():
            raise ValueError("EPO KMS public-keyring configuration is absent")
        try:
            parsed = json.loads(raw)
            config = cls.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError("EPO KMS public-keyring configuration is invalid") from exc
        if config.keyset_purpose != expected_keyset_purpose:
            raise ValueError("EPO KMS public-keyring is bound to the wrong trust boundary")
        return config


def _default_authorized_session() -> Any:
    google_auth = import_module("google.auth")
    transport = import_module("google.auth.transport.requests")
    credentials, _ = google_auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
    return transport.AuthorizedSession(credentials)


class GoogleCloudKMSPublicKeyFetcher:
    """Fetch and integrity-check an Ed25519 public key through the KMS REST API."""

    def __init__(
        self,
        *,
        session_factory: Callable[[], Any] = _default_authorized_session,
        timeout_seconds: float = 10.0,
    ) -> None:
        if timeout_seconds <= 0:
            raise ValueError("KMS timeout must be positive")
        self._session_factory = session_factory
        self._timeout_seconds = timeout_seconds

    async def fetch(self, resource_name: str) -> EPKMSPublicKey:
        return await asyncio.to_thread(self._fetch_sync, resource_name)

    def _fetch_sync(self, resource_name: str) -> EPKMSPublicKey:
        session = self._session_factory()
        response = None
        try:
            response = session.get(
                f"{_KMS_API_ROOT}/{quote(resource_name, safe='/')}/publicKey",
                timeout=self._timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        finally:
            close = getattr(session, "close", None)
            if callable(close):
                close()
        if not isinstance(payload, dict):
            raise ValueError("Cloud KMS returned a malformed public-key response")
        if payload.get("name") != resource_name:
            raise ValueError("Cloud KMS public-key response subject does not match the request")
        if payload.get("algorithm") != "EC_SIGN_ED25519":
            raise ValueError("Cloud KMS key algorithm is not EC_SIGN_ED25519")
        protection_level = payload.get("protectionLevel")
        if not isinstance(protection_level, str) or not protection_level:
            raise ValueError("Cloud KMS response omits the protection level")
        pem = payload.get("pem")
        pem_crc32c = payload.get("pemCrc32c")
        if not isinstance(pem, str) or not pem:
            raise ValueError("Cloud KMS response omits the PEM public key")
        if isinstance(pem_crc32c, bool) or not isinstance(pem_crc32c, (int, str)):
            raise ValueError("Cloud KMS response omits a valid PEM CRC32C")
        try:
            expected_crc32c = int(pem_crc32c)
        except (TypeError, ValueError) as exc:
            raise ValueError("Cloud KMS response omits a valid PEM CRC32C") from exc
        google_crc32c = import_module("google_crc32c")
        actual_crc32c = int(google_crc32c.value(pem.encode("utf-8")))
        if actual_crc32c != expected_crc32c:
            raise ValueError("Cloud KMS PEM CRC32C verification failed")
        public_key = serialization.load_pem_public_key(pem.encode("ascii"))
        if not isinstance(public_key, Ed25519PublicKey):
            raise ValueError("Cloud KMS PEM does not contain an Ed25519 public key")
        raw_public_key = public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return EPKMSPublicKey(
            resource_name=resource_name,
            raw_public_key=raw_public_key,
            algorithm="EC_SIGN_ED25519",
            protection_level=protection_level,
        )


class EPKMSKeyProvider:
    """Load an exact configured keyring from Cloud KMS, then cache immutable versions."""

    def __init__(
        self,
        config: EPKMSKeyringConfig,
        *,
        fetcher: EPKMSPublicKeyFetcher | None = None,
    ) -> None:
        self._config = config
        self._fetcher = fetcher or GoogleCloudKMSPublicKeyFetcher()
        self._lock = asyncio.Lock()
        self._cache: dict[str, EPTrustedAcquisitionKey] | None = None

    async def load_trusted_keys(self) -> Mapping[str, EPTrustedAcquisitionKey]:
        cached = self._cache
        if cached is not None:
            return dict(cached)
        async with self._lock:
            cached = self._cache
            if cached is not None:
                return dict(cached)
            fetched = await asyncio.gather(
                *(
                    self._fetcher.fetch(descriptor.kms_crypto_key_version)
                    for descriptor in self._config.keys
                )
            )
            trusted: dict[str, EPTrustedAcquisitionKey] = {}
            for descriptor, public_key in zip(self._config.keys, fetched, strict=True):
                if public_key.resource_name != descriptor.kms_crypto_key_version:
                    raise ValueError("KMS provider returned a key for another resource")
                if public_key.algorithm != "EC_SIGN_ED25519":
                    raise ValueError("KMS provider returned an unsupported algorithm")
                if public_key.protection_level != descriptor.expected_protection_level:
                    raise ValueError("KMS key protection level differs from governed configuration")
                if (
                    hashlib.sha256(public_key.raw_public_key).hexdigest()
                    != descriptor.expected_public_key_sha256
                ):
                    raise ValueError("KMS public key differs from the governed fingerprint")
                trusted[descriptor.key_id] = EPTrustedAcquisitionKey(
                    key_id=descriptor.key_id,
                    public_key=public_key.raw_public_key,
                    purpose=descriptor.purpose,
                    not_before=descriptor.not_before,
                    not_after=descriptor.not_after,
                    status=descriptor.status,
                    revocation_epoch=descriptor.revocation_epoch,
                    revoked_at=descriptor.revoked_at,
                )
            self._cache = trusted
            return dict(trusted)


class EPCheckpointKMSKeyProvider(EPKMSKeyProvider):
    """Checkpoint-only adapter consumed by ``EPAtomicCheckpointStore``."""

    def __init__(
        self,
        config: EPKMSKeyringConfig,
        *,
        fetcher: EPKMSPublicKeyFetcher | None = None,
    ) -> None:
        if config.keyset_purpose != "checkpoint":
            raise ValueError("checkpoint provider requires a checkpoint KMS keyring")
        super().__init__(config, fetcher=fetcher)

    async def load_trusted_checkpoint_keys(
        self,
    ) -> Mapping[str, EPTrustedAcquisitionKey]:
        return await self.load_trusted_keys()


__all__ = [
    "EPCheckpointKMSKeyProvider",
    "EPKMSKeyDescriptor",
    "EPKMSKeyProvider",
    "EPKMSKeyringConfig",
    "EPKMSPublicKey",
    "EPKMSPublicKeyFetcher",
    "GoogleCloudKMSPublicKeyFetcher",
]
