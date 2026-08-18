from __future__ import annotations

from types import SimpleNamespace

from praviar_pipeline.models.report import MatterEdgeType
from praviar_pipeline.pipeline.runtime.evidence_graph import (
    GraphAccumulator,
    add_auxiliary_nodes_impl,
)


def test_add_auxiliary_nodes_dedupes_ep_register_events_and_classifies_them() -> None:
    graph = GraphAccumulator()

    add_auxiliary_nodes_impl(
        graph=graph,
        patent_id="EP1234567B1",
        patent_node_id="patent:EP1234567B1",
        jurisdiction="EP",
        record=SimpleNamespace(
            has_ptab_proceedings=False,
            has_ep_register_context=True,
            has_orange_book_listing=False,
        ),
        detail=SimpleNamespace(
            designated_states=["DE", "FR"],
            opposition_events=[
                SimpleNamespace(
                    event_code="OPP",
                    event_description="Opposition filed",
                    event_date="2024-06-01",
                )
            ],
            legal_events=[
                SimpleNamespace(
                    event_code="OPP",
                    event_description="Opposition filed",
                    event_date="2024-06-01",
                ),
                SimpleNamespace(
                    event_code="REV",
                    event_description="Patent revoked",
                    event_date="2024-09-10",
                ),
            ],
            orange_book_listed=False,
            ptab_proceedings=[],
        ),
    )

    register_event_nodes = [
        node for node in graph.nodes.values() if node.node_id.startswith("ep_register_event:")
    ]
    tracked_edges = [
        edge
        for edge in graph.edges
        if edge.edge_type == MatterEdgeType.TRACKED_BY
        and edge.from_node_id == "ep_register:EP1234567B1"
    ]

    assert len(register_event_nodes) == 2
    assert {edge.summary for edge in tracked_edges} == {"opposition", "revocation"}
