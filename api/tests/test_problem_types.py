"""Stable RFC 9457 problem-type contract tests."""

import pytest

from api.errors import PROBLEM_TYPE_BASE_URI, APIError, problem_type_uri


def test_problem_types_use_reserved_non_dereferenceable_authority() -> None:
    assert PROBLEM_TYPE_BASE_URI == "https://problems.praviar.invalid/"
    assert problem_type_uri("analysis-capacity-exhausted") == (
        "https://problems.praviar.invalid/analysis-capacity-exhausted"
    )
    assert APIError(503, "Unavailable", "Try later").type_uri == (
        "https://problems.praviar.invalid/service-unavailable"
    )


@pytest.mark.parametrize("slug", ["", "Bad_Slug", "bad/slug", "-bad", "bad-"])
def test_problem_type_slugs_fail_closed(slug: str) -> None:
    with pytest.raises(ValueError, match="lowercase kebab-case"):
        problem_type_uri(slug)
