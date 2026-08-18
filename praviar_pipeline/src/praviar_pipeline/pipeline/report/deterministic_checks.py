"""Deterministic (rule-based) post-LLM integrity checks for FTO reports.

This module provides a pure-Python, LLM-free verification layer that runs
*after* the LLM-based :mod:`praviar_pipeline.pipeline.report_verifier`. Its job is
to catch common LLM failure modes deterministically before reports reach
patent attorneys:

* citations to patents that don't exist in the pipeline data
* quoted claim text that isn't verbatim
* malformed chemical formulas (RDKit round-trip)
* impossible or out-of-term dates
* invalid 2-letter jurisdiction codes
* malformed patent ID formats per jurisdiction
* missing assignees on analyzed patents
* claim counts that exceed what the patent actually has
* element-by-element claim analysis whose sub-counts don't sum
* overall report risk level inconsistent with per-patent max

Each check returns a :class:`DeterministicCheckResult`. Violations carry one
of three severities:

``redact``
    The offending sentence/citation will be removed; the report continues.

``warn``
    Surfaced in the report's audit trail; the report continues.

``block``
    The aggregator raises :class:`ReportIntegrityError` — the pipeline
    fails the analysis rather than ship a broken report.

See SG-123 for the full design rationale.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING, Any, cast

import structlog

from praviar_pipeline.errors import ReportIntegrityError
from praviar_pipeline.models.report_sections import (
    DeterministicCheckResult,
    DeterministicViolation,
)
from praviar_pipeline.utils.safe_diagnostics import safe_exception_type

if TYPE_CHECKING:
    from praviar_pipeline.models.report_sections import ReportSection
    from praviar_pipeline.pipeline.report_data_store import ReportDataStore

logger = structlog.get_logger()


# ── Constants ─────────────────────────────────────────────────────────────

# WIPO ST.3 two-letter country codes (subset sufficient for FTO reports +
# common patent offices; not exhaustive but covers the 9 jurisdictions
# Praviar Pipeline searches plus widely-cited national offices).
VALID_JURISDICTION_CODES: frozenset[str] = frozenset(
    {
        "US",
        "EP",
        "WO",
        "JP",
        "KR",
        "CN",
        "IN",
        "CA",
        "AU",
        "GB",
        "DE",
        "FR",
        "CH",
        "IT",
        "ES",
        "NL",
        "SE",
        "DK",
        "FI",
        "NO",
        "AT",
        "BE",
        "IE",
        "PT",
        "BR",
        "MX",
        "AR",
        "RU",
        "ZA",
        "TW",
        "HK",
        "SG",
        "MY",
        "TH",
        "VN",
        "ID",
        "PH",
        "IL",
        "TR",
        "SA",
        "AE",
        "EG",
        "NZ",
        "CL",
        "CO",
        "PE",
        "UA",
        "PL",
        "CZ",
        "HU",
        "GR",
        "RO",
        "LU",
    }
)

# Per-jurisdiction patent ID regexes. Anchored via \b so they match within
# prose. Permissive on kind-code suffixes but strict on the numeric body.
_PATENT_ID_FORMATS: dict[str, re.Pattern[str]] = {
    "US": re.compile(r"^US\d{7,}(?:[A-Z]\d?)?$"),
    "EP": re.compile(r"^EP\d{7}(?:[AB]\d?)?$"),
    "WO": re.compile(r"^WO\d{4}/?\d{6}(?:[A-Z]\d?)?$"),
    "JP": re.compile(r"^JP(?:H|S|P)?\d{4,}(?:[A-Z]\d?)?$"),
    "KR": re.compile(r"^KR(?:10-)?\d{4,}(?:[A-Z]\d?)?$"),
    "CN": re.compile(r"^CN\d{7,}(?:[A-Z]\d?)?$"),
    "IN": re.compile(r"^IN\d{3,}(?:[A-Z]\d?)?$"),
    "CA": re.compile(r"^CA\d{6,}(?:[A-Z]\d?)?$"),
    "AU": re.compile(r"^AU\d{4,}(?:[A-Z]\d?)?$"),
    "GB": re.compile(r"^GB\d{6,}(?:[A-Z]\d?)?$"),
    "DE": re.compile(r"^DE\d{6,}(?:[A-Z]\d?)?$"),
}

# Patent-ID mentions in prose. Wide net; we cross-check against the data
# store and per-jurisdiction format regex separately.
_PATENT_ID_MENTION_RE = re.compile(
    r"\b(?:"
    r"US\d{6,}(?:[A-Z]\d?)?|"
    r"EP\d{6,}(?:[A-Z]\d?)?|"
    r"WO\d{4}/?\d{4,}(?:[A-Z]\d?)?|"
    r"JP(?:H|S|P)?\d{4,}(?:[A-Z]\d?)?|"
    r"KR(?:10-)?\d{4,}(?:[A-Z]\d?)?|"
    r"CN\d{6,}(?:[A-Z]\d?)?|"
    r"(?:IN|CA|AU|GB|DE|FR|CH)\d{4,}(?:[A-Z]\d?)?"
    r")\b"
)

# ISO-ish date patterns. We parse YYYY-MM-DD to a real date; other formats
# are ignored for term checks (too noisy).
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# Jurisdiction-code mentions — two uppercase letters preceded by whitespace
# or start, followed by a boundary. Filtered to plausible patent/law
# contexts to reduce noise.
_JURISDICTION_MENTION_RE = re.compile(
    r"(?:jurisdiction|country|filed in|granted in|registered in|office)[:\s]+([A-Z]{2})\b",
    re.IGNORECASE,
)

# Quoted-text extraction for claim verbatim check. We match a phrase
# containing "claim <n>" within straight or smart quotes / blockquotes.
_QUOTED_CLAIM_RE = re.compile(
    r'["\u201c\u201d]([^"\u201c\u201d\n]{20,400}?claim\s+\d+[^"\u201c\u201d\n]{0,400}?)["\u201c\u201d]',
    re.IGNORECASE,
)

# SMILES / chemical-formula candidates in prose. Very permissive; we pass
# candidates through RDKit, and only flag ones that *look* like SMILES
# (contain at least one structural character) but fail to parse.
_SMILES_CANDIDATE_RE = re.compile(
    r"(?<![A-Za-z0-9])([A-Za-z0-9@+\-\[\]\(\)=#/\\%]{6,})(?![A-Za-z0-9])"
)
# Strong SMILES chars that distinguish real SMILES from English parenthetical text.
# Parentheses alone match ordinary phrases like "(ANDA)" or "niacinamide)".
_SMILES_STRONG_CHARS = set("=#/\\[]@+%")


# ── Result types ─────────────────────────────────────────────────────────

CheckResult = DeterministicCheckResult  # public alias used in docstrings
Violation = DeterministicViolation


@dataclass(slots=True)
class _Context:
    """Per-run context passed to every check."""

    sections: list[ReportSection]
    data_store: ReportDataStore
    full_text: str


# ── Helper utilities ─────────────────────────────────────────────────────


def _normalize(text: str) -> str:
    """Collapse whitespace for verbatim comparison."""
    return re.sub(r"\s+", " ", text).strip()


def _try_rdkit_parse(smiles: str) -> bool | None:
    """Attempt to parse SMILES via RDKit.

    Returns ``True`` if parsed, ``False`` if RDKit rejected it, ``None`` if
    RDKit is unavailable at runtime (we skip formula checks in that case).
    """
    try:
        from rdkit import (
            Chem,
            RDLogger,
        )
    except ImportError:
        return None

    cast("Any", RDLogger).DisableLog("rdApp.*")  # silence RDKit warnings during checks
    try:
        mol = Chem.MolFromSmiles(smiles, sanitize=True)
    except Exception:
        return False
    return mol is not None


def _looks_like_smiles(candidate: str) -> bool:
    """Heuristic: string is worth sending to RDKit only if it has at least one
    strong structural SMILES character (=, #, /, \\, [, ], @, +, %).
    Parentheses alone appear in ordinary English text and flood the log with
    false positives when the report contains parenthetical phrases."""
    return any(c in _SMILES_STRONG_CHARS for c in candidate)


def _get_total_claims(patent_detail: dict | None) -> int | None:
    """Extract total claim count from a patent detail dict if known."""
    if not patent_detail:
        return None
    for key in ("total_claims", "claim_count", "num_claims"):
        value = patent_detail.get(key)
        if isinstance(value, int) and value > 0:
            return value
    # Fall back to counting entries in a claims list if present.
    claims = patent_detail.get("claims")
    if isinstance(claims, list) and claims:
        return len(claims)
    return None


def _get_claims_text(patent_detail: dict | None) -> str:
    if not patent_detail:
        return ""
    text = patent_detail.get("claims_text")
    return text if isinstance(text, str) else ""


def _patent_jurisdiction(patent_id: str) -> str | None:
    for code in _PATENT_ID_FORMATS:
        if patent_id.upper().startswith(code):
            return code
    return None


def _risk_rank(level: str) -> int:
    """Ordinal rank for risk levels; higher = more risk."""
    return {"clear": 0, "low": 1, "medium": 2, "high": 3}.get(level.lower(), -1)


# ── Individual checks ────────────────────────────────────────────────────


def _check_citation_existence(ctx: _Context) -> CheckResult:
    known = {pid.upper() for pid in ctx.data_store.all_patent_ids()}
    violations: list[Violation] = []
    seen: set[str] = set()
    for match in _PATENT_ID_MENTION_RE.finditer(ctx.full_text):
        patent_id = match.group(0).upper()
        if patent_id in seen:
            continue
        seen.add(patent_id)
        if patent_id not in known:
            violations.append(
                Violation(
                    check_name="citation_existence",
                    severity="redact",
                    detail=f"Unknown patent id '{patent_id}' not present in pipeline data",
                    location=patent_id,
                )
            )
    return CheckResult(
        check_name="citation_existence",
        passed=not violations,
        violations=violations,
    )


def _check_claim_verbatim(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    for section in ctx.sections:
        for match in _QUOTED_CLAIM_RE.finditer(section.content):
            quoted = _normalize(match.group(1))
            # Which patent is this quote attributed to? Use patents_referenced
            # for the section as the search universe.
            candidate_ids = section.patents_referenced or list(ctx.data_store.all_patent_ids())
            matched = False
            checked_any = False
            for pid in candidate_ids:
                detail = ctx.data_store.get_patent_detail(pid)
                claims_text = _normalize(_get_claims_text(detail))
                if not claims_text:
                    continue
                checked_any = True
                if quoted in claims_text:
                    matched = True
                    break
            if checked_any and not matched:
                violations.append(
                    Violation(
                        check_name="claim_verbatim",
                        severity="redact",
                        detail=(
                            "Quoted claim text not found verbatim in any referenced "
                            f"patent: {quoted[:120]}..."
                        ),
                        location=section.section_id,
                    )
                )
    return CheckResult(
        check_name="claim_verbatim",
        passed=not violations,
        violations=violations,
    )


def _check_chemical_formula_parses(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    seen: set[str] = set()

    # Pull explicit SMILES from the compound record (authoritative) and
    # any additional SMILES-looking tokens in the report text.
    candidates: list[str] = []
    compound = getattr(ctx.data_store, "compound", None)
    canonical = getattr(compound, "canonical_smiles", "") if compound else ""
    if canonical:
        candidates.append(canonical)

    for match in _SMILES_CANDIDATE_RE.finditer(ctx.full_text):
        token = match.group(1)
        if _looks_like_smiles(token):
            candidates.append(token)

    for smiles in candidates:
        if smiles in seen:
            continue
        seen.add(smiles)
        result = _try_rdkit_parse(smiles)
        if result is None:
            # RDKit unavailable — note once and stop checking formulas.
            violations.append(
                Violation(
                    check_name="chemical_formula_parses",
                    severity="warn",
                    detail="RDKit not available; chemical formula check skipped",
                    location="",
                )
            )
            break
        if result is False:
            violations.append(
                Violation(
                    check_name="chemical_formula_parses",
                    severity="warn",
                    detail=f"SMILES did not round-trip through RDKit: {smiles[:80]}",
                    location=smiles[:80],
                )
            )
    return CheckResult(
        check_name="chemical_formula_parses",
        passed=not violations,
        violations=violations,
    )


def _check_date_in_term(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    # For every analyzed patent, if it has filing + expiry dates and the
    # report text mentions an ISO date within 50 chars of the patent id,
    # that date must fall inside [filing, expiry].
    for analysis in ctx.data_store.all_analyses():
        detail = ctx.data_store.get_patent_detail(analysis.patent_id) or {}
        filing = _coerce_date(detail.get("filing_date"))
        expiry = _coerce_date(analysis.expiry_date) or _coerce_date(detail.get("expiry_date"))
        if not filing or not expiry:
            continue
        # Find date tokens within 80 chars of every occurrence of the id.
        pattern = re.compile(re.escape(analysis.patent_id), re.IGNORECASE)
        for match in pattern.finditer(ctx.full_text):
            window = ctx.full_text[
                max(0, match.start() - 80) : min(len(ctx.full_text), match.end() + 80)
            ]
            for date_match in _ISO_DATE_RE.finditer(window):
                try:
                    found = date(
                        int(date_match.group(1)),
                        int(date_match.group(2)),
                        int(date_match.group(3)),
                    )
                except ValueError:
                    violations.append(
                        Violation(
                            check_name="date_in_term",
                            severity="warn",
                            detail=f"Impossible date literal '{date_match.group(0)}'",
                            location=analysis.patent_id,
                        )
                    )
                    continue
                if found < filing or found > expiry:
                    violations.append(
                        Violation(
                            check_name="date_in_term",
                            severity="warn",
                            detail=(
                                f"Date {found.isoformat()} for {analysis.patent_id} "
                                f"outside term [{filing.isoformat()}, {expiry.isoformat()}]"
                            ),
                            location=analysis.patent_id,
                        )
                    )
    return CheckResult(
        check_name="date_in_term",
        passed=not violations,
        violations=violations,
    )


def _coerce_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        match = _ISO_DATE_RE.match(value)
        if match:
            try:
                return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
            except ValueError:
                return None
    return None


def _check_jurisdiction_code_valid(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    seen: set[str] = set()
    for match in _JURISDICTION_MENTION_RE.finditer(ctx.full_text):
        code = match.group(1).upper()
        if code in seen:
            continue
        seen.add(code)
        if code not in VALID_JURISDICTION_CODES:
            violations.append(
                Violation(
                    check_name="jurisdiction_code_valid",
                    severity="warn",
                    detail=f"Unknown 2-letter jurisdiction code '{code}'",
                    location=code,
                )
            )
    return CheckResult(
        check_name="jurisdiction_code_valid",
        passed=not violations,
        violations=violations,
    )


def _check_patent_id_format(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    seen: set[str] = set()
    for match in _PATENT_ID_MENTION_RE.finditer(ctx.full_text):
        patent_id = match.group(0).upper().replace(" ", "")
        if patent_id in seen:
            continue
        seen.add(patent_id)
        jurisdiction = _patent_jurisdiction(patent_id)
        if jurisdiction is None:
            violations.append(
                Violation(
                    check_name="patent_id_format",
                    severity="warn",
                    detail=f"Patent id '{patent_id}' has unknown jurisdiction prefix",
                    location=patent_id,
                )
            )
            continue
        pattern = _PATENT_ID_FORMATS[jurisdiction]
        if not pattern.match(patent_id):
            violations.append(
                Violation(
                    check_name="patent_id_format",
                    severity="warn",
                    detail=(
                        f"Patent id '{patent_id}' does not match {jurisdiction} "
                        f"format regex {pattern.pattern}"
                    ),
                    location=patent_id,
                )
            )
    return CheckResult(
        check_name="patent_id_format",
        passed=not violations,
        violations=violations,
    )


def _check_assignee_non_empty(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    for analysis in ctx.data_store.all_analyses():
        if not analysis.assignee or not analysis.assignee.strip():
            violations.append(
                Violation(
                    check_name="assignee_non_empty",
                    severity="warn",
                    detail=f"Patent {analysis.patent_id} has empty assignee",
                    location=analysis.patent_id,
                )
            )
    return CheckResult(
        check_name="assignee_non_empty",
        passed=not violations,
        violations=violations,
    )


def _check_claim_count_sanity(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    for analysis in ctx.data_store.all_analyses():
        analyzed = len(analysis.claims_analyzed)
        detail = ctx.data_store.get_patent_detail(analysis.patent_id)
        total = _get_total_claims(detail)
        if total is not None and analyzed > total:
            violations.append(
                Violation(
                    check_name="claim_count_sanity",
                    severity="block",
                    detail=(
                        f"Patent {analysis.patent_id}: analyzed {analyzed} claims "
                        f"but patent has only {total}"
                    ),
                    location=analysis.patent_id,
                )
            )
    return CheckResult(
        check_name="claim_count_sanity",
        passed=not violations,
        violations=violations,
    )


def _check_element_count_sum(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    from praviar_pipeline.models.analysis_claims import ElementStatus

    for analysis in ctx.data_store.all_analyses():
        for claim in analysis.claims_analyzed:
            total = len(claim.elements)
            found = sum(
                1
                for e in claim.elements
                if e.status in (ElementStatus.MET, ElementStatus.PARTIALLY_MET)
            )
            missing = sum(
                1
                for e in claim.elements
                if e.status in (ElementStatus.NOT_MET, ElementStatus.UNCLEAR)
            )
            if found + missing != total:
                violations.append(
                    Violation(
                        check_name="element_count_sum",
                        severity="block",
                        detail=(
                            f"Patent {analysis.patent_id} claim {claim.claim_number}: "
                            f"found({found}) + missing({missing}) != total({total})"
                        ),
                        location=f"{analysis.patent_id}#claim{claim.claim_number}",
                    )
                )
    return CheckResult(
        check_name="element_count_sum",
        passed=not violations,
        violations=violations,
    )


def _check_risk_level_monotonic(ctx: _Context) -> CheckResult:
    violations: list[Violation] = []
    analyses = ctx.data_store.all_analyses()
    if not analyses:
        return CheckResult(check_name="risk_level_monotonic", passed=True)
    max_rank = max(_risk_rank(a.risk_level.value) for a in analyses)
    overall_rank = _risk_rank(ctx.data_store.overall_risk.value)
    if overall_rank < max_rank:
        violations.append(
            Violation(
                check_name="risk_level_monotonic",
                severity="block",
                detail=(
                    f"Overall risk '{ctx.data_store.overall_risk.value}' is lower than "
                    f"max per-patent risk rank {max_rank}"
                ),
                location="overall",
            )
        )
    return CheckResult(
        check_name="risk_level_monotonic",
        passed=not violations,
        violations=violations,
    )


# ── Public entrypoint ────────────────────────────────────────────────────

_ALL_CHECKS = (
    _check_citation_existence,
    _check_claim_verbatim,
    _check_chemical_formula_parses,
    _check_date_in_term,
    _check_jurisdiction_code_valid,
    _check_patent_id_format,
    _check_assignee_non_empty,
    _check_claim_count_sanity,
    _check_element_count_sum,
    _check_risk_level_monotonic,
)


def run_deterministic_checks(
    sections: list[ReportSection],
    data_store: ReportDataStore,
    *,
    raise_on_block: bool = True,
) -> list[DeterministicCheckResult]:
    """Run every deterministic integrity check over the assembled report.

    Parameters
    ----------
    sections:
        The generated report sections from the deterministic validation stage.
    data_store:
        The pipeline's :class:`ReportDataStore`, used as the source of
        truth for patent existence, claim text, assignees, dates, and
        per-patent risk levels.
    raise_on_block:
        When ``True`` (default), any violation with ``severity="block"``
        raises :class:`ReportIntegrityError` so the orchestrator can
        FAIL the analysis. Set ``False`` to collect all results without
        raising (useful for audit-only runs and unit tests).

    Returns
    -------
    list[DeterministicCheckResult]
        One result per check, in registration order.
    """
    full_text = "\n\n".join(s.content for s in sections if s.word_count > 0)
    ctx = _Context(sections=sections, data_store=data_store, full_text=full_text)

    results: list[DeterministicCheckResult] = []
    blocking: list[Violation] = []
    for check in _ALL_CHECKS:
        try:
            result = check(ctx)
        except Exception as exc:
            logger.error(
                "deterministic_check_failed",
                check=check.__name__,
                error_type=safe_exception_type(exc),
            )
            result = CheckResult(
                check_name=check.__name__.lstrip("_").removeprefix("check_"),
                passed=False,
                violations=[
                    Violation(
                        check_name=check.__name__,
                        severity="block",
                        detail=f"check failed: {safe_exception_type(exc)}",
                    )
                ],
            )
        results.append(result)
        for v in result.violations:
            if v.severity == "block":
                blocking.append(v)

    # Log every non-trivial finding at WARNING level so audit pipelines
    # pick them up even when the pipeline keeps running.
    for result in results:
        for v in result.violations:
            logger.warning(
                "deterministic_check_violation",
                check=result.check_name,
                severity=v.severity,
            )

    if blocking and raise_on_block:
        raise ReportIntegrityError(
            f"Report integrity check found {len(blocking)} blocking violation(s); "
            "refusing to publish.",
            violations=[v.model_dump() for v in blocking],
        )

    return results
