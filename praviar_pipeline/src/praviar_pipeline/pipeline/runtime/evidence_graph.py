"""Matter-graph builders for the evidence-fabric runtime substrate.

This module consolidates the shared graph helpers and accumulator, the
per-patent claim, auxiliary and prosecution node assembly, the patent-level
graph assembly, the summary projection and the top-level matter-graph
builder.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from praviar_pipeline.models.report import (
    MatterEdge,
    MatterEdgeType,
    MatterGraph,
    MatterGraphSummary,
    MatterNode,
    MatterNodeType,
)

if TYPE_CHECKING:
    from praviar_pipeline.models.patent import LegalEvent


def normalize_list(values) -> list:
    return list(values or [])


def node_id(prefix: str, *parts: object) -> str:
    cleaned = [str(part or "").strip() for part in parts if str(part or "").strip()]
    return f"{prefix}:{':'.join(cleaned)}"


def application_label(application_number: str) -> str:
    return application_number or "application"


def office_action_label(patent_id: str, event) -> str:
    office_action_type = str(getattr(event, "office_action_type", "") or "")
    event_date = str(getattr(event, "event_date", "") or "")
    description = str(getattr(event, "description", "") or "")
    parts = [patent_id, office_action_type.replace("_", " "), event_date or description]
    return " ".join(part for part in parts if part).strip()


def amendment_label(patent_id: str, event) -> str:
    event_type = str(getattr(event, "event_type", "") or "")
    event_date = str(getattr(event, "event_date", "") or "")
    description = str(getattr(event, "description", "") or "")
    parts = [patent_id, event_type.replace("_", " "), event_date or description]
    return " ".join(part for part in parts if part).strip()


def claim_numbers_by_patent(claim_program_decisions, analyses) -> dict[str, set[int]]:
    claims: dict[str, set[int]] = defaultdict(set)
    for decision in claim_program_decisions:
        if decision.claim_number > 0:
            claims[decision.patent_id].add(decision.claim_number)
    if claim_program_decisions:
        return claims

    for analysis in analyses or []:
        for claim in getattr(analysis, "claims_analyzed", []) or []:
            claim_number = int(getattr(claim, "claim_number", 0) or 0)
            if claim_number > 0:
                claims[analysis.patent_id].add(claim_number)
    return claims


@dataclass
class GraphAccumulator:
    nodes: dict[str, MatterNode] = field(default_factory=dict)
    edges: list[MatterEdge] = field(default_factory=list)

    def add_node(self, node: MatterNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(
        self,
        edge_type: MatterEdgeType,
        from_node_id: str,
        to_node_id: str,
        summary: str,
    ) -> None:
        edge = MatterEdge(
            edge_type=edge_type,
            from_node_id=from_node_id,
            to_node_id=to_node_id,
            summary=summary,
        )
        if edge not in self.edges:
            self.edges.append(edge)


def add_claim_nodes_impl(
    *,
    graph: GraphAccumulator,
    patent_id: str,
    patent_node_id: str,
    jurisdiction: str,
    claim_numbers: set[int],
) -> None:
    for claim_number in sorted(claim_numbers):
        claim_node_id = f"claim:{patent_id}:{claim_number}"
        graph.add_node(
            MatterNode(
                node_id=claim_node_id,
                node_type=MatterNodeType.CLAIM,
                label=f"{patent_id} claim {claim_number}",
                jurisdiction=jurisdiction,
                patent_id=patent_id,
            )
        )
        graph.add_edge(
            MatterEdgeType.CONTAINS_CLAIM,
            patent_node_id,
            claim_node_id,
            "claim program",
        )


def event_label(patent_id: str, event: LegalEvent) -> str:
    description = str(getattr(event, "event_description", "") or "")
    event_date = str(getattr(event, "event_date", "") or "")
    parts = [patent_id, description or str(getattr(event, "event_code", "") or ""), event_date]
    return " ".join(part for part in parts if part).strip()


def classify_ep_register_event(event: LegalEvent) -> str:
    description = str(getattr(event, "event_description", "") or "").lower()
    code = str(getattr(event, "event_code", "") or "").upper()
    if "opposition" in description or "oppos" in description or code.startswith("OPP"):
        return "opposition"
    if "limitation" in description or "limited" in description or code.startswith("LIM"):
        return "limitation"
    if "revok" in description or code.startswith("REV"):
        return "revocation"
    if (
        "lapse" in description
        or "lapsed" in description
        or "withdraw" in description
        or code.startswith("LAP")
        or code.startswith("WIT")
    ):
        return "lapse_or_withdrawal"
    return "register_event"


def add_auxiliary_nodes_impl(
    *,
    graph: GraphAccumulator,
    patent_id: str,
    patent_node_id: str,
    jurisdiction: str,
    record,
    detail,
) -> None:
    if bool(
        getattr(record, "has_ptab_proceedings", False) or getattr(detail, "ptab_proceedings", None)
    ):
        ptab_node_id = f"ptab:{patent_id}"
        graph.add_node(
            MatterNode(
                node_id=ptab_node_id,
                node_type=MatterNodeType.PTAB_MATTER,
                label=f"{patent_id} PTAB",
                jurisdiction=jurisdiction,
                patent_id=patent_id,
            )
        )
        graph.add_edge(MatterEdgeType.CHALLENGED_BY, patent_node_id, ptab_node_id, "PTAB history")

    if bool(
        getattr(record, "has_ep_register_context", False)
        or getattr(detail, "designated_states", None)
    ):
        _add_ep_register_nodes(
            graph=graph,
            patent_id=patent_id,
            patent_node_id=patent_node_id,
            jurisdiction=jurisdiction,
            detail=detail,
        )

    if bool(
        getattr(record, "has_orange_book_listing", False)
        or getattr(detail, "orange_book_listed", False)
    ):
        orange_node_id = f"orange_book:{patent_id}"
        graph.add_node(
            MatterNode(
                node_id=orange_node_id,
                node_type=MatterNodeType.ORANGE_BOOK_ENTRY,
                label=f"{patent_id} Orange Book",
                jurisdiction=jurisdiction,
                patent_id=patent_id,
            )
        )
        graph.add_edge(
            MatterEdgeType.LISTED_IN,
            patent_node_id,
            orange_node_id,
            "Orange Book listing",
        )


def _add_ep_register_nodes(
    *,
    graph: GraphAccumulator,
    patent_id: str,
    patent_node_id: str,
    jurisdiction: str,
    detail,
) -> None:
    register_node_id = f"ep_register:{patent_id}"
    graph.add_node(
        MatterNode(
            node_id=register_node_id,
            node_type=MatterNodeType.EP_REGISTER_EVENT,
            label=f"{patent_id} register",
            jurisdiction=jurisdiction,
            patent_id=patent_id,
        )
    )
    graph.add_edge(
        MatterEdgeType.TRACKED_BY,
        patent_node_id,
        register_node_id,
        "EP register context",
    )
    seen_event_keys: set[tuple[str, str, str]] = set()
    for index, event in enumerate(
        list(getattr(detail, "opposition_events", []) or [])
        + list(getattr(detail, "legal_events", []) or []),
        start=1,
    ):
        description = str(getattr(event, "event_description", "") or "")
        if not description:
            continue
        event_key = (
            str(getattr(event, "event_date", "") or ""),
            str(getattr(event, "event_code", "") or ""),
            description,
        )
        if event_key in seen_event_keys:
            continue
        seen_event_keys.add(event_key)
        register_event_node_id = node_id("ep_register_event", patent_id, index)
        graph.add_node(
            MatterNode(
                node_id=register_event_node_id,
                node_type=MatterNodeType.EP_REGISTER_EVENT,
                label=event_label(patent_id, event),
                jurisdiction=jurisdiction,
                patent_id=patent_id,
            )
        )
        graph.add_edge(
            MatterEdgeType.TRACKED_BY,
            register_node_id,
            register_event_node_id,
            classify_ep_register_event(event),
        )


def add_prosecution_context_impl(
    *,
    graph: GraphAccumulator,
    patent_id: str,
    jurisdiction: str,
    application_number: str,
    application_node_id: str,
    dossier,
) -> None:
    if not dossier:
        return

    for entry in normalize_list(getattr(dossier, "continuity_entries", [])):
        related_application_number = str(getattr(entry, "application_number", "") or "")
        if not related_application_number:
            continue
        related_application_node_id = node_id("application", related_application_number)
        graph.add_node(
            MatterNode(
                node_id=related_application_node_id,
                node_type=MatterNodeType.APPLICATION,
                label=application_label(related_application_number),
                jurisdiction=jurisdiction,
                patent_id=patent_id,
                application_number=related_application_number,
            )
        )
        graph.add_edge(
            MatterEdgeType.TRACKED_BY,
            application_node_id,
            related_application_node_id,
            (
                f"{getattr(entry, 'relationship', 'related')} "
                f"{getattr(entry, 'continuity_type', 'continuity')}"
            ).strip(),
        )

    for index, event in enumerate(
        normalize_list(getattr(dossier, "office_action_events", [])),
        start=1,
    ):
        office_action_node_id = node_id("office_action", patent_id, index)
        graph.add_node(
            MatterNode(
                node_id=office_action_node_id,
                node_type=MatterNodeType.OFFICE_ACTION,
                label=office_action_label(patent_id, event),
                jurisdiction=jurisdiction,
                patent_id=patent_id,
                application_number=application_number,
            )
        )
        graph.add_edge(
            MatterEdgeType.TRACKED_BY,
            application_node_id,
            office_action_node_id,
            str(getattr(event, "description", "") or "office action record"),
        )

    for index, event in enumerate(
        normalize_list(getattr(dossier, "amendment_events", [])),
        start=1,
    ):
        amendment_node_id = node_id("amendment", patent_id, index)
        graph.add_node(
            MatterNode(
                node_id=amendment_node_id,
                node_type=MatterNodeType.AMENDMENT,
                label=amendment_label(patent_id, event),
                jurisdiction=jurisdiction,
                patent_id=patent_id,
                application_number=application_number,
            )
        )
        graph.add_edge(
            MatterEdgeType.AMENDED_BY,
            application_node_id,
            amendment_node_id,
            str(getattr(event, "description", "") or "amendment history"),
        )


def add_patent_record_graph(
    *,
    graph: GraphAccumulator,
    compound_node_id: str,
    patent_id: str,
    record,
    detail,
    dossier,
    claim_numbers: set[int],
) -> None:
    jurisdiction = getattr(record, "jurisdiction", "") or str(
        getattr(detail, "jurisdiction", "") or ""
    )
    family_id = getattr(record, "family_id", "") or str(
        getattr(getattr(detail, "family", None), "family_id", "") or ""
    )
    application_number = getattr(record, "application_number", "") or str(
        getattr(detail, "application_number", "") or ""
    )

    patent_node_id = f"patent:{patent_id}"
    graph.add_node(
        MatterNode(
            node_id=patent_node_id,
            node_type=MatterNodeType.PATENT,
            label=patent_id,
            jurisdiction=jurisdiction,
            patent_id=patent_id,
            family_id=family_id,
            application_number=application_number,
        )
    )
    graph.add_edge(MatterEdgeType.ROOTS, compound_node_id, patent_node_id, "material patent")

    if family_id:
        family_node_id = f"family:{family_id}"
        graph.add_node(
            MatterNode(
                node_id=family_node_id,
                node_type=MatterNodeType.FAMILY,
                label=family_id,
                family_id=family_id,
            )
        )
        graph.add_edge(
            MatterEdgeType.BELONGS_TO_FAMILY,
            patent_node_id,
            family_node_id,
            "family context",
        )

    if application_number:
        application_node_id = f"application:{application_number}"
        graph.add_node(
            MatterNode(
                node_id=application_node_id,
                node_type=MatterNodeType.APPLICATION,
                label=application_number,
                jurisdiction=jurisdiction,
                patent_id=patent_id,
                application_number=application_number,
            )
        )
        graph.add_edge(
            MatterEdgeType.PROSECUTED_AS,
            patent_node_id,
            application_node_id,
            "application record",
        )
        add_prosecution_context(
            graph=graph,
            patent_id=patent_id,
            jurisdiction=jurisdiction,
            application_number=application_number,
            application_node_id=application_node_id,
            dossier=dossier,
        )

    add_claim_nodes(
        graph=graph,
        patent_id=patent_id,
        patent_node_id=patent_node_id,
        jurisdiction=jurisdiction,
        claim_numbers=claim_numbers,
    )
    add_auxiliary_nodes(
        graph=graph,
        patent_id=patent_id,
        patent_node_id=patent_node_id,
        jurisdiction=jurisdiction,
        record=record,
        detail=detail,
    )


def add_prosecution_context(
    *,
    graph: GraphAccumulator,
    patent_id: str,
    jurisdiction: str,
    application_number: str,
    application_node_id: str,
    dossier,
) -> None:
    add_prosecution_context_impl(
        graph=graph,
        patent_id=patent_id,
        jurisdiction=jurisdiction,
        application_number=application_number,
        application_node_id=application_node_id,
        dossier=dossier,
    )


def add_claim_nodes(
    *,
    graph: GraphAccumulator,
    patent_id: str,
    patent_node_id: str,
    jurisdiction: str,
    claim_numbers: set[int],
) -> None:
    add_claim_nodes_impl(
        graph=graph,
        patent_id=patent_id,
        patent_node_id=patent_node_id,
        jurisdiction=jurisdiction,
        claim_numbers=claim_numbers,
    )


def add_auxiliary_nodes(
    *,
    graph: GraphAccumulator,
    patent_id: str,
    patent_node_id: str,
    jurisdiction: str,
    record,
    detail,
) -> None:
    add_auxiliary_nodes_impl(
        graph=graph,
        patent_id=patent_id,
        patent_node_id=patent_node_id,
        jurisdiction=jurisdiction,
        record=record,
        detail=detail,
    )


def summarize_matter_graph(graph: MatterGraph, *, compound_name: str) -> MatterGraphSummary:
    """Summarize a canonical matter graph for report/API consumers."""
    node_counts = Counter(node.node_type.value for node in graph.nodes)
    edge_counts = Counter(edge.edge_type.value for edge in graph.edges)
    return MatterGraphSummary(
        root_compound=compound_name,
        node_count=len(graph.nodes),
        edge_count=len(graph.edges),
        node_counts_by_type=dict(sorted(node_counts.items())),
        edge_counts_by_type=dict(sorted(edge_counts.items())),
        patent_node_ids=sorted(
            node.node_id for node in graph.nodes if node.node_type == MatterNodeType.PATENT
        ),
        family_node_ids=sorted(
            node.node_id for node in graph.nodes if node.node_type == MatterNodeType.FAMILY
        ),
    )


def build_matter_graph(
    *,
    report,
    matter_evidence_index,
    claim_program_decisions,
    patent_hits: list | None = None,
    analyses: list | None = None,
) -> MatterGraph:
    """Build a compact canonical matter graph for the final matter record."""
    graph = GraphAccumulator()

    compound_label = getattr(report.compound, "name", "") or "compound"
    compound_node_id = f"compound:{compound_label.lower()}"
    graph.add_node(
        MatterNode(
            node_id=compound_node_id,
            node_type=MatterNodeType.COMPOUND_VARIANT,
            label=compound_label,
        )
    )

    dossier_map = {
        dossier.patent_id: dossier for dossier in getattr(report, "prosecution_dossiers", [])
    }
    detail_map = {
        getattr(hit, "patent_id", ""): hit
        for hit in (patent_hits or [])
        if getattr(hit, "patent_id", "")
    }
    claims_by_patent = claim_numbers_by_patent(claim_program_decisions, analyses)

    records_by_patent_id = {
        record.patent_id: record for record in getattr(matter_evidence_index, "patent_records", [])
    }
    patent_ids = sorted(set(records_by_patent_id) | set(detail_map))

    for patent_id in patent_ids:
        add_patent_record_graph(
            graph=graph,
            compound_node_id=compound_node_id,
            patent_id=patent_id,
            record=records_by_patent_id.get(patent_id),
            detail=detail_map.get(patent_id),
            dossier=dossier_map.get(patent_id),
            claim_numbers=claims_by_patent.get(patent_id, set()),
        )

    return MatterGraph(nodes=list(graph.nodes.values()), edges=graph.edges)
