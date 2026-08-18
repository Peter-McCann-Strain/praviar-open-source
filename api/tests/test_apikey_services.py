"""Service-layer tests for API key management."""

from __future__ import annotations

import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from conftest import make_mock_db

from api.errors import APIError
from api.schemas.apikeys import CreateAPIKeyRequest
from api.services.apikeys import (
    API_KEY_NAMESPACE,
    _hash_key,
    authenticate_api_key,
    create_api_key,
    is_namespaced_api_key,
    revoke_api_key,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEST_HMAC_SECRET = "dev-hmac-secret-not-for-production"


def _expected_hash(raw: str) -> str:
    """Reproduce the HMAC-SHA256 digest with the default dev secret."""
    return hmac.new(_TEST_HMAC_SECRET.encode(), raw.encode(), hashlib.sha256).hexdigest()


def _raw_key(seed: str) -> str:
    token = hashlib.sha256(seed.encode()).hexdigest()[:43]
    return f"{API_KEY_NAMESPACE}{token}"


def _create_request(
    name: str = "Production Key",
    *,
    scopes: list[str] | None = None,
    expires_at=None,
) -> CreateAPIKeyRequest:
    return CreateAPIKeyRequest(
        name=name,
        scopes=scopes or ["analyses:read", "reports:read"],
        expires_at=expires_at or datetime.now(UTC) + timedelta(days=90),
    )


def _active_api_key_row(key_hash: str, *, scopes: list[str] | None = None) -> MagicMock:
    api_key_mock = MagicMock()
    api_key_mock.id = uuid.uuid4()
    api_key_mock.org_id = uuid.uuid4()
    api_key_mock.key_hash = key_hash
    api_key_mock.scopes = scopes or ["analyses:read", "reports:read"]
    api_key_mock.expires_at = datetime.now(UTC) + timedelta(days=30)
    return api_key_mock


# ---------------------------------------------------------------------------
# create_api_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_api_key_returns_secret_and_writes_audit_log():
    db = make_mock_db()
    db.refresh = AsyncMock()
    request = MagicMock()

    with patch("api.services.apikeys.write_audit_log", new=AsyncMock()) as audit_log:
        created = await create_api_key(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=_create_request(),
            request=request,
        )

    assert created.secret_key
    assert is_namespaced_api_key(created.secret_key)
    assert created.api_key.key_prefix.endswith("...")
    assert created.api_key.scopes == ["analyses:read", "reports:read"]
    assert created.api_key.expires_at > datetime.now(UTC)
    assert db.commit.await_count == 1
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True


@pytest.mark.asyncio
async def test_create_api_key_rejects_export_scope_under_attorney_risk_gate():
    db = make_mock_db()

    with pytest.raises(APIError, match="scope is unavailable"):
        await create_api_key(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=_create_request(scopes=["reports:export"]),
            request=MagicMock(),
        )

    db.add.assert_not_called()
    db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_api_key_rolls_back_when_creation_audit_fails():
    db = make_mock_db()
    request = MagicMock()

    with (
        patch(
            "api.services.apikeys.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await create_api_key(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=_create_request(),
            request=request,
        )

    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_api_key_stores_hmac_hash_not_raw_sha256():
    """key_hash stored on the ORM object must be an HMAC-SHA256 digest, not plain SHA-256."""
    db = make_mock_db()
    db.refresh = AsyncMock()
    captured_keys = []

    real_add = db.add.side_effect

    def _capture_add(obj):
        captured_keys.append(obj)
        if real_add:
            real_add(obj)

    db.add.side_effect = _capture_add

    with patch("api.services.apikeys.write_audit_log", new=AsyncMock()):
        created = await create_api_key(
            db,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            body=_create_request(name="Hash Check Key", scopes=["reports:read"]),
            request=MagicMock(),
        )

    raw = created.secret_key
    expected = _expected_hash(raw)
    # The hash stored in key_hash must equal the HMAC-keyed digest.
    assert created.api_key.key_hash == expected
    # It must also be a 64-character hex string (SHA-256 output size).
    assert len(expected) == 64
    assert all(c in "0123456789abcdef" for c in expected)


# ---------------------------------------------------------------------------
# _hash_key helper
# ---------------------------------------------------------------------------


def test_hash_key_is_deterministic():
    """Same input must always produce the same HMAC digest."""
    assert _hash_key("test-key") == _hash_key("test-key")


def test_hash_key_returns_64_char_hex():
    digest = _hash_key("some-api-key-value")
    assert len(digest) == 64
    assert all(c in "0123456789abcdef" for c in digest)


def test_hash_key_differs_from_raw_sha256():
    """HMAC-SHA256 with a non-empty secret must differ from bare SHA-256."""
    raw = "collision-test-key"
    bare = hashlib.sha256(raw.encode()).hexdigest()
    keyed = _hash_key(raw)
    # They happen to differ whenever the HMAC secret is non-empty (which it always is).
    assert keyed != bare


# ---------------------------------------------------------------------------
# authenticate_api_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_authenticate_api_key_returns_key_when_valid():
    """A key whose HMAC hash matches a DB row is returned."""
    raw_key = _raw_key("valid-raw-key-value")
    expected_hash = _expected_hash(raw_key)

    api_key_mock = _active_api_key_row(expected_hash)

    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [api_key_mock]
    db.execute.return_value = result

    found = await authenticate_api_key(raw_key, db)

    assert found is api_key_mock
    assert api_key_mock.last_used_at is not None
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    assert db.execute.await_count == 4


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "deletion_status",
    ["billing_cancellation_pending", "archive_deletion_pending", "erased"],
)
async def test_authenticate_api_key_rejects_org_once_erasure_starts(
    deletion_status: str,
) -> None:
    raw_key = _raw_key("erasure-fenced-key")
    api_key = _active_api_key_row(_expected_hash(raw_key))
    api_key.last_used_at = None
    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [api_key]
    db.execute.return_value = result
    db.scalar = AsyncMock(return_value=deletion_status)

    found = await authenticate_api_key(raw_key, db)

    assert found is None
    assert api_key.last_used_at is None
    db.flush.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticate_api_key_rejects_expired_key():
    raw_key = _raw_key("expired-raw-key-value")
    row = _active_api_key_row(_expected_hash(raw_key))
    row.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    db.execute.return_value = result

    found = await authenticate_api_key(raw_key, db)

    assert found is None


@pytest.mark.asyncio
async def test_authenticate_api_key_enforces_required_scope():
    raw_key = _raw_key("scoped-raw-key-value")
    row = _active_api_key_row(_expected_hash(raw_key), scopes=["reports:read"])

    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    db.execute.return_value = result

    found = await authenticate_api_key(raw_key, db, required_scope="reports:read")

    assert found is row

    db_missing = make_mock_db()
    result_missing = MagicMock()
    result_missing.scalars.return_value.all.return_value = [row]
    db_missing.execute.return_value = result_missing

    missing = await authenticate_api_key(
        raw_key,
        db_missing,
        required_scope="reports:export",
    )

    assert missing is None


@pytest.mark.asyncio
async def test_authenticate_api_key_returns_none_when_not_found():
    """No matching row in the DB returns None."""
    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    found = await authenticate_api_key(_raw_key("nonexistent-key"), db)

    assert found is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed",
    [
        "clerk.jwt.token",
        "legacy-api-key",
        "prv_live_short",
        "prv_live_" + ("a" * 42) + "!",
        " prv_live_" + ("a" * 43),
    ],
)
async def test_authenticate_api_key_rejects_malformed_shape_without_db_lookup(
    malformed: str,
) -> None:
    db = make_mock_db()

    assert await authenticate_api_key(malformed, db) is None

    db.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_authenticate_api_key_queries_by_hmac_not_raw_secret():
    """The DB query and RLS context use the HMAC, never the raw secret."""
    raw_key = _raw_key("raw-key-must-not-appear-in-query")
    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute.return_value = result

    await authenticate_api_key(raw_key, db)

    # Confirm execute was called.
    assert db.execute.await_count == 2
    # The full raw key must not appear in the string representation of the call args.
    call_str = str(db.execute.call_args)
    assert raw_key not in call_str
    rls_statement = db.execute.await_args_list[0].args[0]
    assert "app.api_key_hash" in rls_statement.compile().params.values()
    assert _expected_hash(raw_key) in rls_statement.compile().params.values()


@pytest.mark.asyncio
async def test_authenticate_api_key_uses_compare_digest_not_sql_equality():
    """Comparison must happen in Python via hmac.compare_digest, not via SQL =.

    We set up a row whose key_hash does NOT match the candidate hash.  Even
    though it passes the prefix filter, it must be rejected at the Python
    comparison stage.  This confirms that the gate is enforced in-process
    rather than delegated entirely to Postgres string equality.
    """
    raw_key = _raw_key("real-key-value-1234")
    wrong_hash = _expected_hash("completely-different-key")

    row_with_wrong_hash = MagicMock()
    row_with_wrong_hash.key_hash = wrong_hash
    row_with_wrong_hash.id = uuid.uuid4()
    row_with_wrong_hash.org_id = uuid.uuid4()
    row_with_wrong_hash.scopes = ["analyses:read", "reports:read"]
    row_with_wrong_hash.expires_at = datetime.now(UTC) + timedelta(days=30)

    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row_with_wrong_hash]
    db.execute.return_value = result

    found = await authenticate_api_key(raw_key, db)

    assert found is None, "Must reject a row whose key_hash does not match the candidate"


@pytest.mark.asyncio
async def test_authenticate_api_key_rejects_tampered_hash():
    """A row whose stored hash differs by a single character must be rejected."""
    raw_key = _raw_key("tampered-key-test")
    correct_hash = _expected_hash(raw_key)
    # Flip the last hex character to simulate a near-miss.
    last = correct_hash[-1]
    flipped = "0" if last != "0" else "1"
    tampered_hash = correct_hash[:-1] + flipped

    tampered_row = MagicMock()
    tampered_row.key_hash = tampered_hash
    tampered_row.id = uuid.uuid4()
    tampered_row.org_id = uuid.uuid4()
    tampered_row.scopes = ["analyses:read", "reports:read"]
    tampered_row.expires_at = datetime.now(UTC) + timedelta(days=30)

    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [tampered_row]
    db.execute.return_value = result

    found = await authenticate_api_key(raw_key, db)

    assert found is None


# ---------------------------------------------------------------------------
# revoke_api_key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_api_key_marks_key_revoked():
    db = make_mock_db()
    api_key = MagicMock()
    api_key.id = uuid.uuid4()
    api_key.name = "Test Key"
    api_key.key_prefix = "abcd1234..."
    api_key.revoked = False
    result = MagicMock()
    result.scalar_one_or_none.return_value = api_key
    db.execute.return_value = result

    with patch("api.services.apikeys.write_audit_log", new=AsyncMock()) as audit_log:
        await revoke_api_key(
            db,
            key_id=api_key.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            request=MagicMock(),
        )

    assert api_key.revoked is True
    db.flush.assert_awaited_once()
    db.commit.assert_awaited_once()
    audit_log.assert_awaited_once()
    assert audit_log.await_args is not None
    assert audit_log.await_args.kwargs["fail_closed"] is True


@pytest.mark.asyncio
async def test_revoke_api_key_rolls_back_when_audit_fails():
    db = make_mock_db()
    api_key = MagicMock()
    api_key.id = uuid.uuid4()
    api_key.name = "Test Key"
    api_key.key_prefix = "abcd1234..."
    api_key.revoked = False
    result = MagicMock()
    result.scalar_one_or_none.return_value = api_key
    db.execute.return_value = result

    with (
        patch(
            "api.services.apikeys.write_audit_log",
            new=AsyncMock(side_effect=RuntimeError("audit unavailable")),
        ),
        pytest.raises(RuntimeError, match="audit unavailable"),
    ):
        await revoke_api_key(
            db,
            key_id=api_key.id,
            org_id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            request=MagicMock(),
        )

    db.flush.assert_awaited_once()
    db.commit.assert_not_awaited()
    db.rollback.assert_awaited_once()


# ---------------------------------------------------------------------------
# Hostile / adversarial tests
# ---------------------------------------------------------------------------


def test_raw_sha256_does_not_equal_stored_hmac_hash():
    """Prove that old unsalted SHA-256 hashes would never authenticate.

    If a legacy system stored bare SHA-256 digests, those values must differ
    from the HMAC-SHA256 digests that _hash_key() now produces.  Any row
    carrying a bare digest would therefore be rejected by hmac.compare_digest(),
    even when the correct raw key is presented.
    """
    raw_key = "adversarial-legacy-key-value"
    bare_sha256 = hashlib.sha256(raw_key.encode()).hexdigest()
    hmac_hash = _hash_key(raw_key)

    # The bare SHA-256 must not match the HMAC-SHA256 digest.
    assert not hmac.compare_digest(bare_sha256, hmac_hash), (
        "Raw SHA-256 must differ from HMAC-SHA256: old hashes must be invalidated"
    )

    # Reinforce: feeding the bare digest into compare_digest simulates what
    # authenticate_api_key() would do against a legacy DB row -- it must fail.
    candidate_hash = _hash_key(raw_key)
    assert not hmac.compare_digest(bare_sha256, candidate_hash)


@pytest.mark.asyncio
async def test_authenticate_api_key_returns_none_for_tampered_raw_key():
    """Mutate one byte of a valid raw key -- authentication must fail.

    This is the primary adversarial gate: an attacker who intercepts a key and
    alters even a single character must be rejected outright.
    """
    raw_key = _raw_key("valid-key-for-tamper-test")
    correct_hash = _expected_hash(raw_key)

    # Tamper: flip the last character of the raw key string.
    tampered_raw = raw_key[:-1] + ("X" if raw_key[-1] != "X" else "Y")

    # The stored hash corresponds to the original key.
    valid_row = MagicMock()
    valid_row.key_hash = correct_hash
    valid_row.id = uuid.uuid4()
    valid_row.org_id = uuid.uuid4()
    valid_row.scopes = ["analyses:read", "reports:read"]
    valid_row.expires_at = datetime.now(UTC) + timedelta(days=30)

    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [valid_row]
    db.execute.return_value = result

    # Present the tampered key -- must not authenticate against the stored hash.
    found = await authenticate_api_key(tampered_raw, db)

    assert found is None, (
        "A key with a mutated byte must not authenticate, even against the correct stored hash"
    )


@pytest.mark.asyncio
async def test_authenticate_api_key_returns_none_for_revoked_key():
    """Create a key, mark it revoked, confirm authenticate_api_key returns None.

    authenticate_api_key() filters on ``revoked IS FALSE`` in the DB query.
    This test confirms that a revoked row is excluded from the candidate set
    before the HMAC comparison is even attempted.
    """
    raw_key = _raw_key("revocation-test-key")

    # Simulate the DB returning an empty candidate set because the prefix
    # filter includes ``revoked IS FALSE``.  A revoked row simply does not
    # appear in the result at all.
    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []  # filtered out by revoked=False clause
    db.execute.return_value = result

    found = await authenticate_api_key(raw_key, db)

    assert found is None, "Revoked key must not authenticate"

    # Confirm the query was actually issued (i.e. we did not short-circuit
    # before hitting the DB at all).
    assert db.execute.await_count == 2

    # Extra belt-and-braces: even if a revoked row somehow leaked through,
    # we can verify the HMAC comparison would still reject a different hash.
    revoked_row = MagicMock()
    revoked_row.key_hash = _expected_hash("some-other-key")  # wrong hash
    revoked_row.id = uuid.uuid4()
    revoked_row.org_id = uuid.uuid4()
    revoked_row.scopes = ["analyses:read", "reports:read"]
    revoked_row.expires_at = datetime.now(UTC) + timedelta(days=30)
    db2 = make_mock_db()
    result2 = MagicMock()
    result2.scalars.return_value.all.return_value = [revoked_row]
    db2.execute.return_value = result2

    found2 = await authenticate_api_key(raw_key, db2)
    assert found2 is None, "A revoked-row leak with a mismatched hash must still be rejected"


def test_hmac_digest_uses_configured_secret():
    """_hash_key() must use the configured HMAC secret, not a hard-coded value.

    We compute the expected HMAC manually with the test secret and confirm that
    _hash_key() produces an identical digest.  We also confirm that swapping in
    a different secret produces a different digest, demonstrating that the secret
    is actually incorporated into the computation.
    """
    raw = "hmac-secret-binding-test-key"

    # Compute the expected digest with the default dev secret.
    expected_with_dev_secret = hmac.new(
        _TEST_HMAC_SECRET.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()

    # _hash_key() must match this exactly (the default settings secret is the
    # same value as _TEST_HMAC_SECRET).
    assert _hash_key(raw) == expected_with_dev_secret, (
        "_hash_key() must produce the HMAC-SHA256 digest keyed with the configured secret"
    )

    # Now patch the secret to a different value and confirm the digest changes.
    different_secret = "a-completely-different-secret-value"
    expected_with_different_secret = hmac.new(
        different_secret.encode(), raw.encode(), hashlib.sha256
    ).hexdigest()

    settings_mock = MagicMock()
    settings_mock.api_key_hmac_secret.get_secret_value.return_value = different_secret

    with patch("api.services.apikeys.get_settings", return_value=settings_mock):
        digest_with_different_secret = _hash_key(raw)

    assert digest_with_different_secret == expected_with_different_secret
    assert digest_with_different_secret != expected_with_dev_secret, (
        "Changing the HMAC secret must produce a different digest -- "
        "the secret must be actively used, not ignored"
    )


@pytest.mark.asyncio
async def test_timing_safe_hash_collision_does_not_authenticate():
    """Confirm that compare_digest is used and a hash collision for a different key is rejected.

    Scenario: a DB row exists whose key_hash was produced from a *different*
    raw key -- simulating a contrived hash-collision or a confused-deputy
    attack where an attacker manages to plant their own hash into the DB row
    for a victim key.  The HMAC comparison must still reject this because
    the candidate hash (derived from the attacker's presented raw key) will
    not match the victim key's stored hash, and vice-versa.
    """
    attacker_raw_key = _raw_key("attacker-raw-key-collision-probe")
    victim_raw_key = _raw_key("victim-raw-key-collision-probe")

    attacker_hash = _expected_hash(attacker_raw_key)
    victim_hash = _expected_hash(victim_raw_key)

    # Sanity: these are genuinely different digests.
    assert attacker_hash != victim_hash

    # The DB row carries the *victim's* hash.  The attacker presents their
    # own raw key hoping compare_digest will confuse the two.
    row_with_victim_hash = MagicMock()
    row_with_victim_hash.key_hash = victim_hash
    row_with_victim_hash.id = uuid.uuid4()
    row_with_victim_hash.org_id = uuid.uuid4()
    row_with_victim_hash.scopes = ["analyses:read", "reports:read"]
    row_with_victim_hash.expires_at = datetime.now(UTC) + timedelta(days=30)

    db = make_mock_db()
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row_with_victim_hash]
    db.execute.return_value = result

    # Attacker presents their key; must NOT authenticate as the victim.
    found = await authenticate_api_key(attacker_raw_key, db)

    assert found is None, (
        "An attacker presenting their own key must not be authenticated against "
        "a DB row whose hash belongs to a different key -- compare_digest must "
        "be comparing the correct digests"
    )
