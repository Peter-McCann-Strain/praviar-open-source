"""Result builders and report-internal evidence searchers.

Operates on already-loaded report data; no outbound network or DB calls.

This module is a thin facade that re-exports the full public surface so that
callers see an unchanged import path. The implementation is split across two
sub-modules:

- :mod:`api.services.report_evidence_searchers` -- per-section search
  functions that return :class:`EvidenceSearchResultResponse` lists.
- :mod:`api.services.report_evidence_builders` -- provider-capability
  builders, merge helpers, and the top-level search orchestrator.
"""

from __future__ import annotations

# Standard-library and schema re-exports retained to preserve the public
# symbol set expected by callers that inspect this module's namespace.
import uuid  # noqa: F401
from typing import Any  # noqa: F401

from api.schemas.report_evidence_search import (  # noqa: F401
    EvidenceSearchFollowUpTargetResponse,
    EvidenceSearchProvenanceItemResponse,
    EvidenceSearchProviderCapabilityResponse,
    EvidenceSearchResponse,
    EvidenceSearchResultResponse,
    EvidenceSearchScopeResponse,
)
from api.services import report_external_evidence  # noqa: F401
from api.services.report_evidence_builders import (
    build_external_result,
    build_provider_capabilities,
    build_scope,
    has_active_hybrid_layer,
    has_live_external_provider,
    merge_coverage_values,
    merge_provider_capabilities,
    merge_text_notes,
    provider_notice_result,
    search_report_evidence_impl,
)
from api.services.report_evidence_filter import (  # noqa: F401
    PROVIDER_EXECUTION_PRIORITY,
    PROVIDER_STATUS_PRIORITY,
    classify_provider,
    collect_jurisdictions,
    collect_modalities,
    collect_sources,
    excerpt,
    external_retrieval_allowed,
    matches,
    provider_id_from_source,
    text,
)
from api.services.report_evidence_searchers import (
    build_follow_up,
    build_provenance,
    search_adapter_results,
    search_coverage_and_uncertainty,
    search_evidence_artifacts,
    search_family_records,
    search_patent_records,
    search_prosecution_dossiers,
    search_search_loop,
)

__all__ = [
    # filter re-exports
    "PROVIDER_EXECUTION_PRIORITY",
    "PROVIDER_STATUS_PRIORITY",
    "classify_provider",
    "collect_jurisdictions",
    "collect_modalities",
    "collect_sources",
    "excerpt",
    "external_retrieval_allowed",
    "matches",
    "provider_id_from_source",
    "text",
    # searchers
    "build_follow_up",
    "build_provenance",
    "search_adapter_results",
    "search_coverage_and_uncertainty",
    "search_evidence_artifacts",
    "search_family_records",
    "search_patent_records",
    "search_prosecution_dossiers",
    "search_search_loop",
    # builders
    "build_external_result",
    "build_provider_capabilities",
    "build_scope",
    "has_active_hybrid_layer",
    "has_live_external_provider",
    "merge_coverage_values",
    "merge_provider_capabilities",
    "merge_text_notes",
    "provider_notice_result",
    "search_report_evidence_impl",
]
