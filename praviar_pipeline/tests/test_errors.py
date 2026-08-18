"""Tests for praviar_pipeline.errors — custom exception hierarchy."""

from praviar_pipeline.errors import (
    AllSourcesFailedError,
    AuthenticationError,
    ClientError,
    ConfigurationError,
    InsufficientDataError,
    LLMResponseError,
    PatCIDDatabaseNotFoundError,
    PraviarPipelineError,
    RateLimitError,
    SearchError,
)


class TestPraviarPipelineError:
    def test_message_preserved(self):
        err = PraviarPipelineError("something broke")
        assert str(err) == "something broke"

    def test_source_and_step_defaults(self):
        err = PraviarPipelineError("msg")
        assert err.source == ""
        assert err.step == ""

    def test_source_and_step_kwargs(self):
        err = PraviarPipelineError("msg", source="pubchem", step="resolve")
        assert err.source == "pubchem"
        assert err.step == "resolve"

    def test_is_exception(self):
        assert issubclass(PraviarPipelineError, Exception)


class TestSearchError:
    def test_inherits_praviar_pipeline_error(self):
        assert issubclass(SearchError, PraviarPipelineError)

    def test_preserves_attrs(self):
        err = SearchError("search failed", source="bigquery", step="search")
        assert err.source == "bigquery"
        assert err.step == "search"


class TestAllSourcesFailedError:
    def test_formats_failures_dict(self):
        failures = {"pubchem": "timeout", "bigquery": "403 forbidden"}
        err = AllSourcesFailedError(failures)
        assert "pubchem: timeout" in str(err)
        assert "bigquery: 403 forbidden" in str(err)
        assert "All search sources failed" in str(err)

    def test_step_set_to_search(self):
        err = AllSourcesFailedError({"src": "err"})
        assert err.step == "search"

    def test_failures_dict_stored(self):
        failures = {"a": "1", "b": "2"}
        err = AllSourcesFailedError(failures)
        assert err.failures == failures

    def test_inherits_search_error(self):
        assert issubclass(AllSourcesFailedError, SearchError)

    def test_empty_failures(self):
        err = AllSourcesFailedError({})
        assert "All search sources failed" in str(err)


class TestClientError:
    def test_inherits_praviar_pipeline_error(self):
        assert issubclass(ClientError, PraviarPipelineError)


class TestAuthenticationError:
    def test_inherits_client_error(self):
        assert issubclass(AuthenticationError, ClientError)

    def test_message(self):
        err = AuthenticationError("bad key", source="epo")
        assert str(err) == "bad key"
        assert err.source == "epo"


class TestPatCIDDatabaseNotFoundError:
    def test_includes_path_in_message(self):
        err = PatCIDDatabaseNotFoundError("/data/patcid.db")
        assert "/data/patcid.db" in str(err)

    def test_source_is_patcid(self):
        err = PatCIDDatabaseNotFoundError("/any/path")
        assert err.source == "patcid"

    def test_inherits_client_error(self):
        assert issubclass(PatCIDDatabaseNotFoundError, ClientError)


class TestConfigurationError:
    def test_inherits_praviar_pipeline_error(self):
        assert issubclass(ConfigurationError, PraviarPipelineError)

    def test_message(self):
        err = ConfigurationError("missing API key")
        assert str(err) == "missing API key"


class TestInsufficientDataError:
    def test_inherits_praviar_pipeline_error(self):
        assert issubclass(InsufficientDataError, PraviarPipelineError)


class TestLLMResponseError:
    def test_model_stored_as_source(self):
        err = LLMResponseError("parse failed", model="claude-opus-4-6", step="analysis")
        assert err.source == "claude-opus-4-6"
        assert err.step == "analysis"

    def test_inherits_praviar_pipeline_error(self):
        assert issubclass(LLMResponseError, PraviarPipelineError)

    def test_defaults(self):
        err = LLMResponseError("bad json")
        assert err.source == ""
        assert err.step == ""


class TestRateLimitError:
    def test_inherits_client_error(self):
        assert issubclass(RateLimitError, ClientError)

    def test_message(self):
        err = RateLimitError("429 too many requests", source="semantic_scholar")
        assert str(err) == "429 too many requests"
        assert err.source == "semantic_scholar"
