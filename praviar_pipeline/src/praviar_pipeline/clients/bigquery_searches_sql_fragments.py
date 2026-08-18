"""Shared SQL fragments for BigQuery patent search queries."""

from __future__ import annotations

PUBLICATION_SELECT_COLUMNS = """
    p.publication_number,
    (SELECT t.text FROM UNNEST(p.title_localized) AS t
     WHERE t.language = 'en' LIMIT 1) AS title,
    (SELECT a.text FROM UNNEST(p.abstract_localized) AS a
     WHERE a.language = 'en' LIMIT 1) AS abstract,
    p.filing_date,
    p.priority_date,
    p.assignee_harmonized,
    p.inventor_harmonized
""".strip()

PUBLICATION_SELECT_COLUMNS_WITH_CPC = """
    p.publication_number,
    (SELECT t.text FROM UNNEST(p.title_localized) AS t
     WHERE t.language = 'en' LIMIT 1) AS title,
    (SELECT a.text FROM UNNEST(p.abstract_localized) AS a
     WHERE a.language = 'en' LIMIT 1) AS abstract,
    p.filing_date,
    p.priority_date,
    p.assignee_harmonized,
    p.inventor_harmonized,
    ARRAY(SELECT c.code FROM UNNEST(p.cpc) AS c) AS cpc_codes
""".strip()

TRANSLATED_PUBLICATION_SELECT_COLUMNS = """
    p.publication_number,
    COALESCE(
        (SELECT t.text FROM UNNEST(p.title_localized) AS t
         WHERE t.language = 'en' LIMIT 1),
        (SELECT t.text FROM UNNEST(p.title_localized) AS t
         LIMIT 1)
    ) AS title,
    COALESCE(
        (SELECT a.text FROM UNNEST(p.abstract_localized) AS a
         WHERE a.language = 'en' LIMIT 1),
        (SELECT a.text FROM UNNEST(p.abstract_localized) AS a
         LIMIT 1)
    ) AS abstract,
    p.filing_date,
    p.priority_date,
    p.assignee_harmonized,
    ARRAY(SELECT c.code FROM UNNEST(p.cpc) AS c) AS cpc_codes
""".strip()


def build_publication_search_sql(*, select_columns: str, extra_where_clause: str) -> str:
    return f"""
        SELECT
            {select_columns}
        FROM
            `patents-public-data.patents.publications` p
        WHERE
            EXISTS (SELECT 1 FROM UNNEST(p.title_localized) AS t
                    WHERE t.language = 'en')
            AND EXISTS (SELECT 1 FROM UNNEST(p.abstract_localized) AS a
                        WHERE a.language = 'en')
            {extra_where_clause}
        ORDER BY p.grant_date DESC
        LIMIT @max_results
    """
