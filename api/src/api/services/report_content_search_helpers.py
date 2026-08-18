"""Internal helpers for report content keyword search."""

from __future__ import annotations

from typing import Any


def _build_snippet(text: str, query_text: str, *, padding: int = 60) -> str:
    query_lower = query_text.lower()
    idx = text.lower().find(query_lower)
    start = max(0, idx - padding)
    end = min(len(text), idx + len(query_text) + padding)
    return ("..." if start > 0 else "") + text[start:end] + ("..." if end < len(text) else "")


def _build_result(
    *,
    patent_id: str,
    section: str,
    relevance: float,
    snippet: str,
) -> dict[str, Any]:
    return {
        "patent_id": patent_id,
        "section": section,
        "relevance": relevance,
        "snippet": snippet,
    }


def _search_patent_analyses(report: dict, query_text: str) -> list[dict[str, Any]]:
    query_lower = query_text.lower()
    results = []

    for patent_analysis in report.get("patent_analyses", []):
        if not isinstance(patent_analysis, dict):
            continue
        patent_id = patent_analysis.get("patent_id", "")
        title = patent_analysis.get("title", "")
        risk_summary = patent_analysis.get("risk_summary", "")
        searchable = f"{title} {risk_summary} {patent_id}".lower()

        if query_lower in searchable:
            results.append(
                _build_result(
                    patent_id=patent_id,
                    section="patent_analysis",
                    relevance=1.0 if query_lower in title.lower() else 0.7,
                    snippet=_build_snippet(f"{title}. {risk_summary}", query_text),
                )
            )

    return results


def _search_risk_summary(report: dict, query_text: str) -> list[dict[str, Any]]:
    query_lower = query_text.lower()
    executive_summary = report.get("risk_summary", {}).get("executive_summary", "")

    if query_lower in executive_summary.lower():
        return [
            _build_result(
                patent_id="",
                section="executive_summary",
                relevance=0.9,
                snippet=_build_snippet(executive_summary, query_text),
            )
        ]

    return []


def _search_assessment_section(
    items: list[Any],
    *,
    query_text: str,
    section: str,
    relevance: float,
    text_key: str = "reasoning",
) -> list[dict[str, Any]]:
    query_lower = query_text.lower()
    results = []

    for item in items:
        if not isinstance(item, dict):
            continue
        reasoning = item.get(text_key, "")
        if query_lower in reasoning.lower():
            results.append(
                _build_result(
                    patent_id=item.get("patent_id", ""),
                    section=section,
                    relevance=relevance,
                    snippet=_build_snippet(reasoning, query_text),
                )
            )

    return results


def search_report_content_impl(report: dict, query_text: str) -> dict:
    """Search report content via keyword matching over core narrative sections."""
    results = []
    results.extend(_search_patent_analyses(report, query_text))
    results.extend(_search_risk_summary(report, query_text))
    results.extend(
        _search_assessment_section(
            report.get("doe_assessments", []),
            query_text=query_text,
            section="doe_assessment",
            relevance=0.6,
        )
    )
    results.extend(
        _search_assessment_section(
            report.get("invalidity_assessments", []),
            query_text=query_text,
            section="invalidity_assessment",
            relevance=0.5,
        )
    )

    results.sort(key=lambda result: result["relevance"], reverse=True)
    return {
        "query": query_text,
        "interpreted_query": f'Keyword search: "{query_text}"',
        "results": results[:20],
        "total": len(results),
    }
