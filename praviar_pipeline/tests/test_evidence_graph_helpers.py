from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.report import MatterEdgeType, MatterNodeType
from praviar_pipeline.pipeline.runtime.evidence_graph import (
    GraphAccumulator,
    add_patent_record_graph,
    claim_numbers_by_patent,
)


def test_claim_numbers_by_patent_falls_back_to_analyses_when_decisions_missing() -> None:
    analyses = [
        SimpleNamespace(
            patent_id="US123",
            claims_analyzed=[
                SimpleNamespace(claim_number=1),
                SimpleNamespace(claim_number=2),
                SimpleNamespace(claim_number=0),
            ],
        )
    ]

    claim_numbers = claim_numbers_by_patent([], analyses)

    assert claim_numbers == {"US123": {1, 2}}


def test_add_patent_record_graph_adds_prosecution_and_auxiliary_nodes() -> None:
    graph = GraphAccumulator()
    dossier = SimpleNamespace(
        continuity_entries=[
            SimpleNamespace(
                application_number="US09/999999",
                relationship="parent",
                continuity_type="continuation",
            )
        ],
        office_action_events=[
            SimpleNamespace(
                office_action_type="restriction_requirement",
                event_date="2024-01-01",
                description="Restriction issued",
            )
        ],
        amendment_events=[
            SimpleNamespace(
                event_type="amendment",
                event_date="2024-03-01",
                description="Claim amendment filed",
            )
        ],
    )

    add_patent_record_graph(
        graph=graph,
        compound_node_id="compound:aspirin",
        patent_id="US1234567B2",
        record=SimpleNamespace(
            jurisdiction="US",
            family_id="fam-1",
            application_number="US10/000001",
            has_ptab_proceedings=True,
            has_ep_register_context=False,
            has_orange_book_listing=True,
        ),
        detail=SimpleNamespace(ptab_proceedings=[], orange_book_listed=False),
        dossier=dossier,
        claim_numbers={1, 2},
    )

    node_types = {node.node_type for node in graph.nodes.values()}
    edge_types = {edge.edge_type for edge in graph.edges}

    assert MatterNodeType.PATENT in node_types
    assert MatterNodeType.APPLICATION in node_types
    assert MatterNodeType.FAMILY in node_types
    assert MatterNodeType.CLAIM in node_types
    assert MatterNodeType.OFFICE_ACTION in node_types
    assert MatterNodeType.AMENDMENT in node_types
    assert MatterNodeType.PTAB_MATTER in node_types
    assert MatterNodeType.ORANGE_BOOK_ENTRY in node_types
    assert MatterEdgeType.ROOTS in edge_types
    assert MatterEdgeType.PROSECUTED_AS in edge_types
    assert MatterEdgeType.CONTAINS_CLAIM in edge_types
    assert MatterEdgeType.AMENDED_BY in edge_types
    assert MatterEdgeType.CHALLENGED_BY in edge_types
    assert MatterEdgeType.LISTED_IN in edge_types


def test_add_patent_record_graph_adds_ep_register_event_nodes() -> None:
    graph = GraphAccumulator()

    add_patent_record_graph(
        graph=graph,
        compound_node_id="compound:aspirin",
        patent_id="EP2345678B1",
        record=SimpleNamespace(
            jurisdiction="EP",
            family_id="fam-ep",
            application_number="",
            has_ptab_proceedings=False,
            has_ep_register_context=True,
            has_orange_book_listing=False,
        ),
        detail=SimpleNamespace(
            designated_states=["DE", "FR"],
            legal_events=[
                SimpleNamespace(
                    event_code="OPP",
                    event_description="Opposition filed",
                    event_date="2024-06-01",
                )
            ],
            opposition_events=[
                SimpleNamespace(
                    event_code="OPP",
                    event_description="Opposition filed",
                    event_date="2024-06-01",
                )
            ],
            orange_book_listed=False,
        ),
        dossier=None,
        claim_numbers=set(),
    )

    labels = {node.label for node in graph.nodes.values()}
    edge_summaries = {edge.summary for edge in graph.edges}

    assert "EP2345678B1 register" in labels
    assert any("Opposition filed" in label for label in labels)
    assert "opposition" in edge_summaries
