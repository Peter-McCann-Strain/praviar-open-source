"""Deterministic parsing helpers for patent claims."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import structlog

logger = structlog.get_logger()

TRANSITIONAL_PHRASES = [
    "consisting essentially of",
    "consisting of",
    "comprising",
    "including",
    "containing",
    "characterized by",
    "wherein the improvement comprises",
]

_DEP_CLAIM_RE = re.compile(
    r"(?:the\s+)?(?:method|composition|compound|process|system|device|apparatus|"
    r"product|article|kit|formulation|pharmaceutical|combination|use|claim)\s+"
    r"(?:of|according\s+to|as\s+(?:defined|claimed|set\s+forth)\s+in)\s+"
    r"claim\s+(\d+)",
    re.IGNORECASE,
)

_DEP_CLAIM_ALT_RE = re.compile(
    r"^(?:claim|claims?)\s+(\d+)\s*,\s*(?:wherein|where|further|additionally)",
    re.IGNORECASE,
)


@dataclass
class ParsedElement:
    """A single claim element/limitation."""

    element_number: int
    element_text: str


@dataclass
class ParsedClaim:
    """A deterministically parsed patent claim."""

    claim_number: int
    raw_text: str
    claim_type: str
    depends_on: int | None
    preamble: str
    transitional_phrase: str
    elements: list[ParsedElement] = field(default_factory=list)


def split_claims(claims_text: str) -> list[ParsedClaim]:
    """Split raw claims text into individual parsed claims."""
    if not claims_text or not claims_text.strip():
        return []

    text = claims_text.strip()
    claim_blocks = _split_numbered_claims(text)
    if not claim_blocks:
        logger.warning("claim_parser_no_numbered_claims", text_length=len(text))
        claim_blocks = [(1, text)]

    parsed = [_parse_single_claim(claim_num, raw_text) for claim_num, raw_text in claim_blocks]
    logger.debug(
        "claims_parsed",
        total_claims=len(parsed),
        independent=sum(1 for claim in parsed if claim.claim_type == "independent"),
        dependent=sum(1 for claim in parsed if claim.claim_type == "dependent"),
    )
    return parsed


def _split_numbered_claims(text: str) -> list[tuple[int, str]]:
    """Split text into (claim_number, claim_text) pairs."""
    pattern = r"(?:^|\n)\s*(\d{1,3})\s*\.\s+"
    matches = list(re.finditer(pattern, text))
    if not matches:
        pattern = r"(?:^|\n)\s*[Cc]laim\s+(\d{1,3})\s*[.:]\s*"
        matches = list(re.finditer(pattern, text))
    if not matches:
        return []

    blocks: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        claim_num = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        claim_text = text[start:end].strip()
        if claim_text.endswith("."):
            claim_text = claim_text[:-1].strip()
        blocks.append((claim_num, claim_text))
    return blocks


def _parse_single_claim(claim_num: int, raw_text: str) -> ParsedClaim:
    """Parse a single claim into preamble, transitional phrase, and elements."""
    claim_type = "independent"
    depends_on: int | None = None

    dep_match = _DEP_CLAIM_RE.search(raw_text) or _DEP_CLAIM_ALT_RE.search(raw_text)
    if dep_match:
        claim_type = "dependent"
        depends_on = int(dep_match.group(1))

    preamble = ""
    transitional = ""
    body = raw_text

    text_lower = raw_text.lower()
    for phrase in TRANSITIONAL_PHRASES:
        index = text_lower.find(phrase)
        if index != -1:
            preamble = raw_text[:index].strip().rstrip(",:")
            transitional = phrase
            body = raw_text[index + len(phrase) :].strip().lstrip(":").strip()
            break

    return ParsedClaim(
        claim_number=claim_num,
        raw_text=raw_text,
        claim_type=claim_type,
        depends_on=depends_on,
        preamble=preamble,
        transitional_phrase=transitional,
        elements=_split_elements(body),
    )


def _split_elements(body: str) -> list[ParsedElement]:
    """Split claim body into individual elements/limitations."""
    if not body.strip():
        return [ParsedElement(element_number=1, element_text=body.strip())]

    if ";" in body:
        raw_elements = [element.strip() for element in body.split(";") if element.strip()]
    elif re.search(r"\([a-z]\)", body) or re.search(r"\([ivx]+\)", body):
        raw_elements = [
            part.strip() for part in re.split(r"(?=\([a-z]\)|\([ivx]+\))", body) if part.strip()
        ]
    elif "wherein" in body.lower():
        raw_elements = [
            part.strip()
            for part in re.split(r"\s+(?=wherein\b)", body, flags=re.IGNORECASE)
            if part.strip()
        ]
    else:
        raw_elements = [body.strip()]

    elements = []
    for index, text in enumerate(raw_elements, start=1):
        text = text.strip().rstrip(";").rstrip(".").strip()
        if text:
            elements.append(ParsedElement(element_number=index, element_text=text))

    return elements if elements else [ParsedElement(element_number=1, element_text=body.strip())]
