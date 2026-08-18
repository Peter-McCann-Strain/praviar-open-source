"""Tests for cursor-based pagination helpers in api.services.analyses.

Covers _encode_cursor, _decode_cursor, and the CursorPage schema.
Uses Hypothesis for property-based tests.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

UTC = UTC


def _import_helpers():
    from api.services.analyses import _decode_cursor, _encode_cursor

    return _encode_cursor, _decode_cursor


class TestCursorEncoding:
    def test_roundtrip_preserves_created_at_and_id(self):
        encode, decode = _import_helpers()
        created_at = datetime(2026, 5, 29, 10, 0, 0, tzinfo=UTC)
        analysis_id = uuid.UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6")
        cursor = encode(created_at, analysis_id)
        decoded_ts, decoded_id = decode(cursor)
        assert decoded_id == analysis_id
        assert abs((decoded_ts - created_at).total_seconds()) < 1

    def test_cursor_is_url_safe_string(self):
        encode, _ = _import_helpers()
        cursor = encode(datetime(2026, 1, 1, tzinfo=UTC), uuid.uuid4())
        assert "+" not in cursor
        assert "/" not in cursor
        assert " " not in cursor

    def test_cursor_is_opaque_non_empty_string(self):
        encode, _ = _import_helpers()
        cursor = encode(datetime(2026, 1, 1, tzinfo=UTC), uuid.uuid4())
        assert isinstance(cursor, str)
        assert len(cursor) > 0

    def test_different_timestamps_produce_different_cursors(self):
        encode, _ = _import_helpers()
        id_ = uuid.uuid4()
        c1 = encode(datetime(2026, 1, 1, tzinfo=UTC), id_)
        c2 = encode(datetime(2026, 1, 2, tzinfo=UTC), id_)
        assert c1 != c2

    def test_different_ids_produce_different_cursors(self):
        encode, _ = _import_helpers()
        ts = datetime(2026, 1, 1, tzinfo=UTC)
        assert encode(ts, uuid.uuid4()) != encode(ts, uuid.uuid4())


class TestCursorDecoding:
    def test_decode_invalid_base64_raises_value_error(self):
        _, decode = _import_helpers()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode("not-valid-base64!!!")

    def test_decode_missing_pipe_raises_value_error(self):
        import base64

        _, decode = _import_helpers()
        bad = base64.urlsafe_b64encode(b"no-pipe-separator").decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode(bad)

    def test_decode_bad_uuid_raises_value_error(self):
        import base64

        _, decode = _import_helpers()
        bad = base64.urlsafe_b64encode(b"2026-01-01T00:00:00+00:00|not-a-uuid").decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode(bad)

    def test_decode_bad_timestamp_raises_value_error(self):
        import base64

        _, decode = _import_helpers()
        uid = str(uuid.uuid4())
        bad = base64.urlsafe_b64encode(f"not-a-date|{uid}".encode()).decode()
        with pytest.raises(ValueError, match="Invalid cursor"):
            decode(bad)

    def test_decode_empty_string_raises_value_error(self):
        _, decode = _import_helpers()
        with pytest.raises(ValueError):
            decode("")


try:
    from hypothesis import given
    from hypothesis import settings as h_settings
    from hypothesis import strategies as st

    HAS_HYPOTHESIS = True
except ImportError:
    HAS_HYPOTHESIS = False


@pytest.mark.skipif(not HAS_HYPOTHESIS, reason="hypothesis not installed")
class TestCursorPropertyBased:
    """Property-based tests: encode/decode must roundtrip for all valid inputs."""

    @given(  # type: ignore[possibly-undefined]
        ts=st.datetimes(  # type: ignore[possibly-undefined]
            min_value=datetime(2020, 1, 1),
            max_value=datetime(2030, 12, 31),
            timezones=st.just(UTC),  # type: ignore[possibly-undefined]
        ),
        uid=st.uuids(),  # type: ignore[possibly-undefined]
    )
    @h_settings(max_examples=50)  # type: ignore[possibly-undefined]
    def test_encode_decode_roundtrip(self, ts, uid):
        encode, decode = _import_helpers()
        cursor = encode(ts, uid)
        decoded_ts, decoded_id = decode(cursor)
        assert decoded_id == uid
        assert abs((decoded_ts - ts).total_seconds()) < 1

    @given(st.text(min_size=1, max_size=200))  # type: ignore[possibly-undefined]
    @h_settings(max_examples=50)  # type: ignore[possibly-undefined]
    def test_decode_arbitrary_string_raises_or_returns_valid(self, s):
        """Any string input either decodes cleanly or raises ValueError -- never crashes."""
        _, decode = _import_helpers()
        try:
            decoded_ts, decoded_id = decode(s)
            assert isinstance(decoded_ts, datetime)
            assert isinstance(decoded_id, uuid.UUID)
        except ValueError:
            pass
