"""USPTO ODP (Open Data Portal) Lucene query builders.

Replaces the decommissioned PatentsView search.patentsview.org API which was
shut down on 2026-03-20. The USPTO ODP API at api.uspto.gov accepts Lucene
syntax queries against the patent file wrapper database.

Key queryable fields:
  applicationMetaData.inventionTitle:{term}
  applicationMetaData.cpcClassificationBag:{prefix}*  (wildcard required)
  applicationMetaData.patentNumber:{num}
  assignmentBag.assigneeBag.assigneeNameText:{name}

Important: cpcClassificationBag stores values like "A61K   8/0216" (with
internal whitespace). The ODP Lucene index does not tokenise on spaces within
the CPC string, so a bare prefix like "A61K" returns zero results. A trailing
wildcard ("A61K*") is required for any prefix-style CPC filter.
"""

from __future__ import annotations

import re


def _cpc_prefix_term(cpc_prefix: str) -> str:
    """Append wildcard to a CPC prefix if not already present."""
    p = cpc_prefix.rstrip("*")
    return f"applicationMetaData.cpcClassificationBag:{p}*"


def build_cpc_search_query(cpc_prefix: str, keywords: list[str] | None = None) -> str:
    """Build Lucene query by CPC class prefix with optional title keyword filter."""
    parts = [_cpc_prefix_term(cpc_prefix)]
    if keywords:
        kw_clause = " OR ".join(
            f'applicationMetaData.inventionTitle:"{_q(kw)}"' for kw in keywords[:5]
        )
        parts.append(f"({kw_clause})")
    return " AND ".join(parts)


def build_assignee_search_query(assignee_name: str) -> str:
    """Build Lucene query by assignee name."""
    return f'assignmentBag.assigneeBag.assigneeNameText:"{_q(assignee_name)}"'


def build_patent_query(patent_id: str) -> str:
    """Build Lucene query for a single granted patent by number."""
    num = _strip_patent_id(patent_id)
    return f"applicationMetaData.patentNumber:{num}"


def build_compound_keyword_query(
    compound_name: str,
    synonyms: list[str] | None = None,
    *,
    cpc_prefix: str = "A61K",
) -> str:
    """Build Lucene query for compound keyword search restricted to a CPC class.

    Searches invention titles for the compound name or synonyms while
    restricting to a CPC classification prefix for pharmaceutical relevance.
    A trailing wildcard is appended to the CPC prefix automatically — the ODP
    index requires it for prefix matching (bare "A61K" returns zero results).
    """
    terms = [compound_name, *(synonyms or [])[:9]]
    title_clause = " OR ".join(f'applicationMetaData.inventionTitle:"{_q(t)}"' for t in terms)
    return f"{_cpc_prefix_term(cpc_prefix)} AND ({title_clause})"


def _q(text: str) -> str:
    """Escape special Lucene characters inside a double-quoted field value."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _strip_patent_id(patent_id: str) -> str:
    """Strip US country prefix and kind suffix from a patent number string."""
    num = patent_id.strip()
    if num.upper().startswith("US"):
        num = num[2:]
    num = re.sub(r"[A-Z]\d*$", "", num).rstrip("-")
    return num
