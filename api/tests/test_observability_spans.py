from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from api.observability import spans


def test_set_current_span_attributes_filters_non_scalar_values(monkeypatch):
    span = MagicMock()
    trace = SimpleNamespace(get_current_span=lambda: span)
    monkeypatch.setattr(spans, "import_module", lambda name: trace)

    spans.set_current_span_attributes(
        {
            "tenant.id": "org-1",
            "nested": {"not": "allowed"},
            "count": 3,
        }
    )

    span.set_attributes.assert_called_once_with({"tenant.id": "org-1", "count": 3})


def test_start_span_does_not_swallow_application_exceptions(monkeypatch):
    class FakeTracer:
        @contextmanager
        def start_as_current_span(self, _name):
            yield MagicMock()

    trace = SimpleNamespace(get_tracer=lambda _name: FakeTracer())
    monkeypatch.setattr(spans, "import_module", lambda name: trace)

    try:
        with spans.start_span("test.operation"):
            raise RuntimeError("must propagate")
    except RuntimeError as exc:
        assert str(exc) == "must propagate"
    else:
        raise AssertionError("start_span swallowed an application exception")


def test_start_span_noops_when_otel_is_unavailable(monkeypatch):
    def missing(_name):
        raise ImportError("no otel")

    monkeypatch.setattr(spans, "import_module", missing)

    with spans.start_span("test.operation") as span:
        assert span is None
