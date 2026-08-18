"""Patent ID normalization utilities."""

from __future__ import annotations

import re
from datetime import UTC, datetime

_KIND_CODES = re.compile(r"(A[1-9]?|B[1-3]?|C[1-3]|E|H|S|P[1-3])$")

# Tier mapping for FTO-correct deduplication (Option C).
#
# For Freedom-to-Operate analysis the grant/application distinction is
# legally significant: A-tier documents (published applications) carry no
# enforceable claims, while B-tier documents (granted patents) do.
# Collapsing across tiers would allow a granted patent to be discarded as a
# duplicate of a previously-seen application, producing false negatives in the
# risk assessment.
#
# Within a tier we *do* collapse (A1→A, A2→A, …) because the same application
# published in two slightly different forms is the same document for FTO
# purposes.
#
# Kind codes not listed here (U1/U2 utility models, S design patents, H
# statutory invention registrations, etc.) are kept verbatim so they form
# their own dedup bucket.
_A_TIER = re.compile(r"^A[1-9]?$")
_B_TIER = re.compile(r"^B[1-4]?$|^B[89]$")
_C_TIER = re.compile(r"^C[1-3]?$")

_SUPPORTED_PUBLICATION_JURISDICTIONS = frozenset(
    {
        "AT",
        "AU",
        "BE",
        "BR",
        "CA",
        "CH",
        "CN",
        "CZ",
        "DE",
        "DK",
        "EA",
        "EP",
        "ES",
        "FI",
        "FR",
        "GB",
        "GR",
        "HK",
        "HU",
        "IE",
        "IL",
        "IN",
        "IT",
        "JP",
        "KR",
        "MX",
        "MY",
        "NL",
        "NO",
        "NZ",
        "PL",
        "PT",
        "RU",
        "SE",
        "SG",
        "SK",
        "TR",
        "TW",
        "US",
        "WO",
        "ZA",
    }
)
_PUBLICATION_CORE_PATTERNS: dict[str, re.Pattern[str]] = {
    "AT": re.compile(r"^\d{6,7}$"),
    "AU": re.compile(r"^\d{6,10}$"),
    "BE": re.compile(r"^\d{6,7}$"),
    "BR": re.compile(r"^\d{7,13}$"),
    "CA": re.compile(r"^\d{7}$"),
    "CH": re.compile(r"^\d{6,7}$"),
    "CN": re.compile(r"^\d{7,13}$"),
    "CZ": re.compile(r"^\d{5,8}$"),
    "DE": re.compile(r"^\d{7,12}$"),
    "DK": re.compile(r"^\d{6,10}$"),
    "EA": re.compile(r"^\d{5,9}$"),
    "EP": re.compile(r"^\d{7}$"),
    "ES": re.compile(r"^\d{6,8}$"),
    "FI": re.compile(r"^\d{5,10}$"),
    "FR": re.compile(r"^\d{7}$"),
    "GB": re.compile(r"^\d{7}$"),
    "GR": re.compile(r"^\d{6,10}$"),
    "HK": re.compile(r"^\d{7,10}$"),
    "HU": re.compile(r"^\d{5,8}$"),
    "IE": re.compile(r"^\d{5,9}$"),
    "IL": re.compile(r"^\d{5,7}$"),
    "IN": re.compile(r"^\d{6,12}$"),
    "IT": re.compile(r"^\d{6,12}$"),
    "JP": re.compile(r"^(?:(?:19|20)\d{7,10}|[HST]\d{6,10}|\d{5,10})$"),
    "KR": re.compile(r"^\d{7,13}$"),
    "MX": re.compile(r"^\d{6,12}$"),
    "MY": re.compile(r"^\d{6,12}$"),
    "NL": re.compile(r"^\d{6,9}$"),
    "NO": re.compile(r"^\d{6,10}$"),
    "NZ": re.compile(r"^\d{5,7}$"),
    "PL": re.compile(r"^\d{5,8}$"),
    "PT": re.compile(r"^\d{5,8}$"),
    "RU": re.compile(r"^\d{7,13}$"),
    "SE": re.compile(r"^\d{6,10}$"),
    "SG": re.compile(r"^\d{6,12}$"),
    "SK": re.compile(r"^\d{5,8}$"),
    "TR": re.compile(r"^\d{6,12}$"),
    "TW": re.compile(r"^\d{7,12}$"),
    "US": re.compile(r"^(?:\d{5,12}|D\d{5,9}|PP\d{4,8}|RE\d{4,8}|H\d{3,8}|T\d{5,9})$"),
    "WO": re.compile(r"^(?:19|20)\d{8}$"),
    "ZA": re.compile(r"^\d{6,10}$"),
}

_PUBLICATION_KIND_CODES: dict[str, frozenset[str]] = {
    "AT": frozenset(
        {"A", "A1", "A2", "A3", "A4", "A5", "A8", "A9", "B", "B1", "B2", "B8", "B9", "U1", "U2"}
    ),
    "AU": frozenset({"A", "A1", "A2", "A4", "A8", "A9", "B", "B1", "B2", "B3", "C1"}),
    "BE": frozenset(
        {"A", "A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9", "B1", "B2", "B3", "B8", "B9"}
    ),
    "BR": frozenset({"A", "A1", "A2", "B1", "B2", "C1", "C2", "U2", "Y1"}),
    "CA": frozenset({"A", "A1", "B", "B1", "B2", "C"}),
    "CH": frozenset(
        {
            "A",
            "A1",
            "A2",
            "A3",
            "A4",
            "A5",
            "A6",
            "A7",
            "A8",
            "A9",
            "B",
            "B1",
            "B2",
            "B3",
            "B4",
            "B5",
            "B6",
            "B7",
            "B8",
            "B9",
        }
    ),
    "CN": frozenset({"A", "B", "C", "S", "U", "Y"}),
    "CZ": frozenset({"A3", "B6", "U1"}),
    "DE": frozenset({"A1", "A5", "A8", "A9", "B3", "B4", "C1", "C2", "U1"}),
    "DK": frozenset({"A", "A1", "A3", "B1", "B3", "U1", "Y1"}),
    "EA": frozenset({"A1", "A2", "B1"}),
    "EP": frozenset({"A1", "A2", "A3", "A4", "A8", "A9", "B1", "B2", "B3", "B8", "B9"}),
    "ES": frozenset({"A1", "A2", "A8", "A9", "B1", "B2", "U"}),
    "FI": frozenset({"A", "A1", "A2", "A3", "B", "B1", "U"}),
    "FR": frozenset({"A", "A1", "A2", "A3", "A5", "A6", "A7", "B1", "B3"}),
    "GB": frozenset({"A", "A1", "A2", "A3", "A8", "A9", "B", "B1", "B2", "B8"}),
    "GR": frozenset({"A", "A1", "A2", "A3", "B", "B1", "B2", "U"}),
    "HK": frozenset({"A", "A0", "A1", "A2", "B", "B1", "B2"}),
    "HU": frozenset({"A", "A1", "A2", "A3", "B", "B1", "B2", "U"}),
    "IE": frozenset({"A", "A1", "A2", "B", "B1", "B2", "S"}),
    "IL": frozenset({"A", "A1", "B", "B1", "B2"}),
    "IN": frozenset({"A", "A1", "A2", "B", "B1", "B2"}),
    "IT": frozenset({"A", "A1", "A2", "A3", "A4", "B", "B1", "B2", "U"}),
    "JP": frozenset({"A", "B1", "B2", "U", "Y"}),
    "KR": frozenset({"A", "A1", "B1", "B2", "U", "Y"}),
    "MX": frozenset({"A", "A1", "A2", "B", "B1", "B2", "U"}),
    "MY": frozenset({"A", "A1", "A2", "B", "B1", "B2"}),
    "NL": frozenset({"A", "A1", "A2", "A3", "B", "B1", "B2", "C", "C1", "C2"}),
    "NO": frozenset({"A", "A1", "B", "B1", "C", "C1"}),
    "NZ": frozenset({"A", "A1", "B", "B1"}),
    "PL": frozenset({"A1", "A3", "B1", "U1", "Y1"}),
    "PT": frozenset({"A", "A1", "A2", "B", "B1", "U"}),
    "RU": frozenset({"A", "A1", "A2", "A3", "B", "B1", "B2", "C", "C1", "C2", "U1"}),
    "SE": frozenset({"A", "A1", "B", "B1", "C", "C1"}),
    "SG": frozenset({"A", "A1", "B", "B1"}),
    "SK": frozenset({"A3", "B6", "U1"}),
    "TR": frozenset({"A", "A1", "A2", "B", "B1", "U"}),
    "TW": frozenset({"A", "A1", "A2", "B", "B1", "B2", "U"}),
    "US": frozenset(
        {
            "A",
            "A1",
            "A2",
            "A9",
            "B",
            "B1",
            "B2",
            "B3",
            "C",
            "C1",
            "E",
            "H",
            "I1",
            "I2",
            "P",
            "P1",
            "P2",
            "P3",
            "P4",
            "S",
            "S1",
        }
    ),
    "WO": frozenset({"A1", "A2", "A3", "A4", "A8", "A9"}),
    "ZA": frozenset({"A", "A1", "B", "B1"}),
}

if set(_PUBLICATION_CORE_PATTERNS) != _SUPPORTED_PUBLICATION_JURISDICTIONS:
    raise RuntimeError("publication core-format policy does not cover every supported office")
if set(_PUBLICATION_KIND_CODES) != _SUPPORTED_PUBLICATION_JURISDICTIONS:
    raise RuntimeError("publication kind-code policy does not cover every supported office")


def _has_valid_publication_body(jurisdiction: str, body: str) -> bool:
    core_pattern = _PUBLICATION_CORE_PATTERNS[jurisdiction]
    if core_pattern.fullmatch(body) and _has_valid_publication_period(jurisdiction, body):
        return True
    for kind_code in sorted(_PUBLICATION_KIND_CODES[jurisdiction], key=len, reverse=True):
        core = body[: -len(kind_code)]
        if (
            body.endswith(kind_code)
            and core_pattern.fullmatch(core)
            and _has_valid_publication_period(jurisdiction, core)
        ):
            return True
    return False


def _has_valid_publication_period(jurisdiction: str, core: str) -> bool:
    if jurisdiction == "WO":
        year = int(core[:4])
        return 1978 <= year <= datetime.now(UTC).year + 1
    if jurisdiction == "JP" and core[0] in {"H", "S", "T"}:
        era_year = int(core[1:3])
        return 1 <= era_year <= {"H": 31, "S": 64, "T": 15}[core[0]]
    return True


def _canonical_kind(kind: str) -> str:
    """Return the canonical tier letter for a kind code, or the code itself."""
    if not kind:
        # No kind code → treat as B-tier (most common for older granted patents
        # cited without a suffix, e.g. "US7851188").
        return "B"
    k = kind.upper()
    if _A_TIER.match(k):
        return "A"
    if _B_TIER.match(k):
        return "B"
    if _C_TIER.match(k):
        return "C"
    # Unknown kind codes (U1, S, H, P1, E, …) are kept as-is so they form
    # their own dedup bucket rather than silently collapsing.
    return k


def normalize_patent_id(patent_id: str) -> str:
    """Normalize patent ID for FTO-correct deduplication.

    Applies three transformations:
    1. Uppercase + strip punctuation (commas, spaces, hyphens).
    2. Canonicalize country prefix.
    3. Collapse kind code *within tier* (A1/A2→A, B1/B2→B, C1/C2→C) but
       keep tier distinct so that an application (A-tier) and the corresponding
       grant (B-tier) never map to the same dedup key.

    Examples::

        >>> normalize_patent_id("EP1234567A1")
        'EP1234567A'
        >>> normalize_patent_id("EP1234567B1")
        'EP1234567B'
        >>> normalize_patent_id("US7851188")   # no kind code → B-tier
        'US7851188B'
        >>> normalize_patent_id("US7851188B2")
        'US7851188B'
    """
    pid = patent_id.upper().replace(",", "").replace(" ", "").replace("-", "")
    pid = re.sub(r"^(US|EP|WO|JP|CN|KR|AU|CA|GB|DE|FR|IN)", r"\1", pid)
    m = _KIND_CODES.search(pid)
    if m:
        base = pid[: m.start()]
        kind = m.group(1)
    else:
        base = pid
        kind = ""
    return base + _canonical_kind(kind)


def canonical_publication_id(patent_id: str) -> str:
    """Return a normalized supported publication identifier.

    This intentionally rejects PCT application identifiers and arbitrary
    two-letter prefixes. Decisioning operates on publication identifiers; PCT
    applications must first be resolved to their WO publication number.
    """
    raw = str(patent_id or "").strip().upper()
    if not raw or raw.startswith("PCT/") or "/" in raw:
        raise ValueError(f"unsupported patent publication identifier: {patent_id}")
    normalized = re.sub(r"[\s,.-]", "", raw)
    if len(normalized) < 7:
        raise ValueError(f"unsupported patent publication identifier: {patent_id}")
    jurisdiction = normalized[:2]
    body = normalized[2:]
    if jurisdiction not in _SUPPORTED_PUBLICATION_JURISDICTIONS:
        raise ValueError(f"unsupported patent publication jurisdiction: {patent_id}")
    if not _has_valid_publication_body(jurisdiction, body):
        raise ValueError(f"unsupported patent publication identifier: {patent_id}")
    return normalized


def publication_jurisdiction(patent_id: str) -> str:
    """Return the jurisdiction encoded by a supported publication identifier."""
    normalized = canonical_publication_id(patent_id)
    jurisdiction = normalized[:2]
    if jurisdiction not in _SUPPORTED_PUBLICATION_JURISDICTIONS:  # defensive totality
        raise ValueError(f"unsupported US patent publication identifier: {patent_id}")
    return jurisdiction


def strip_kind_code(patent_id: str) -> str:
    """Strip only the kind code, preserving the rest."""
    return _KIND_CODES.sub("", patent_id.strip())


def clean_patent_number_for_api(patent_id: str) -> str:
    """Clean patent number for PTAB/USPTO ODP API calls."""
    pid = patent_id.upper().replace(",", "").replace(" ", "")
    if pid.startswith("US"):
        pid = pid[2:]
    return _KIND_CODES.sub("", pid)
