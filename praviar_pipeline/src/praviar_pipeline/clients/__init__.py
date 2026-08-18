"""External API clients for Praviar Pipeline.

The package exposes client classes lazily so importing a lightweight client
module does not pull in every optional upstream SDK.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_CLIENT_EXPORTS = {
    "BigQueryClient": "praviar_pipeline.clients.bigquery",
    "ClaudeClient": "praviar_pipeline.clients.claude",
    "EPOOPSClient": "praviar_pipeline.clients.epo_ops",
    "EPOPublicationServerClient": "praviar_pipeline.clients.epo_publication_server",
    "LensClient": "praviar_pipeline.clients.lens",
    "OpenAlexClient": "praviar_pipeline.clients.openalex",
    "OpenFDAGSRSClient": "praviar_pipeline.clients.openfda_gsrs",
    "PTABClient": "praviar_pipeline.clients.ptab",
    "PatCIDClient": "praviar_pipeline.clients.patcid",
    "PubChemClient": "praviar_pipeline.clients.pubchem",
    "SemanticScholarClient": "praviar_pipeline.clients.semantic_scholar",
    "SureChEMBLClient": "praviar_pipeline.clients.surechembl",
    "USPTOODPClient": "praviar_pipeline.clients.uspto_odp",
}


def __getattr__(name: str) -> Any:
    if name not in _CLIENT_EXPORTS:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(_CLIENT_EXPORTS[name])
    value = getattr(module, name)
    globals()[name] = value
    return value


__all__ = [
    "BigQueryClient",
    "ClaudeClient",
    "EPOOPSClient",
    "EPOPublicationServerClient",
    "LensClient",
    "OpenAlexClient",
    "OpenFDAGSRSClient",
    "PTABClient",
    "PatCIDClient",
    "PubChemClient",
    "SemanticScholarClient",
    "SureChEMBLClient",
    "USPTOODPClient",
]
