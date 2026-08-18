"""Response parsers for the EPO OPS client."""

from __future__ import annotations


def _as_list(value):
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _first_dict(value) -> dict:
    for item in _as_list(value):
        if isinstance(item, dict):
            return item
    return {}


def _text(value) -> str:
    if isinstance(value, dict):
        return str(value.get("$", "") or "").strip()
    if value is None:
        return ""
    return str(value).strip()


def _nested_text(value, *keys: str) -> str:
    current = value
    for key in keys:
        if not isinstance(current, dict):
            return ""
        current = current.get(key)
    return _text(current)


def _first_text(*values) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def parse_search_results(data: dict) -> list[dict]:
    """Parse OPS published-data search results into publication dicts."""
    results: list[dict] = []
    search_result = (
        data.get("ops:world-patent-data", {})
        .get("ops:biblio-search", {})
        .get("ops:search-result", {})
        .get("ops:publication-reference", [])
    )

    if isinstance(search_result, dict):
        search_result = [search_result]

    for pub_ref in search_result:
        doc_ids = pub_ref.get("document-id", [])
        if isinstance(doc_ids, dict):
            doc_ids = [doc_ids]
        for doc_id in doc_ids:
            if doc_id.get("@document-id-type") == "docdb":
                country = doc_id.get("country", {}).get("$", "")
                doc_number = doc_id.get("doc-number", {}).get("$", "")
                kind = doc_id.get("kind", {}).get("$", "")
                if country and doc_number:
                    results.append(
                        {
                            "publication_number": f"{country}{doc_number}{kind}",
                            "country": country,
                            "doc_number": doc_number,
                            "kind": kind,
                        }
                    )
    return results


def parse_legal_status(data: dict) -> list[dict]:
    """Parse INPADOC legal events from the documented OPS Legal response.

    A legacy Register-shaped response is retained as an input variant because
    historical cassettes used that shape.  Both variants preserve the event
    exchange timestamps needed to assess source freshness.
    """
    events: list[dict] = []
    family = data.get("ops:world-patent-data", {}).get("ops:patent-family", {})
    for member in _as_list(family.get("ops:family-member", [])):
        if not isinstance(member, dict):
            continue
        country = _nested_text(
            _first_dict(member.get("publication-reference", {})).get(
                "document-id",
                {},
            ),
            "country",
        )
        for legal in _as_list(member.get("ops:legal", [])):
            if not isinstance(legal, dict):
                continue
            events.append(
                {
                    "event_date": _first_text(
                        legal.get("ops:L007EP"),
                        legal.get("ops:L007"),
                    ),
                    "event_code": _first_text(
                        legal.get("@code"),
                        legal.get("ops:L008EP"),
                        legal.get("ops:L008"),
                    ),
                    "event_description": _text(legal.get("@desc")),
                    "country": country,
                    "date_last_exchanged": _first_text(
                        legal.get("ops:L018EP"),
                        legal.get("ops:L018"),
                    ),
                    "date_first_created": _first_text(
                        legal.get("ops:L019EP"),
                        legal.get("ops:L019"),
                    ),
                    "influence": _text(legal.get("@infl")),
                }
            )

    legacy_documents = (
        data.get("ops:world-patent-data", {})
        .get("ops:register-search", {})
        .get("reg:register-documents", {})
        .get("reg:register-document", [])
    )
    for doc in _as_list(legacy_documents):
        if not isinstance(doc, dict):
            continue
        biblio = doc.get("reg:bibliographic-data", {})
        for evt in _as_list(biblio.get("reg:events", {}).get("reg:event", [])):
            if not isinstance(evt, dict):
                continue
            event_info = evt.get("reg:event-data", {})
            events.append(
                {
                    "event_date": _text(event_info.get("reg:event-date")),
                    "event_code": _text(event_info.get("reg:event-code")),
                    "event_description": _text(event_info.get("reg:event-description")),
                    "country": _text(event_info.get("reg:event-country")),
                    "date_last_exchanged": "",
                    "date_first_created": "",
                    "influence": "",
                }
            )
    return events


_OPS_FAMILY_APPLICATION_IDENTITY_SOURCE = "epo_ops_family.application-reference.docdb"


def _explicit_family_application_number(member: dict) -> str:
    """Return one unambiguous DOCDB application identifier from an OPS member.

    OPS family records identify the application separately from each
    publication.  Only the documented DOCDB ``application-reference`` is
    authoritative here; publication numbers and opaque ``doc-id`` attributes
    are deliberately not used as substitutes.
    """
    candidates: set[str] = set()
    for application_reference in _as_list(member.get("application-reference", [])):
        if not isinstance(application_reference, dict):
            continue
        for document_id in _as_list(application_reference.get("document-id", [])):
            if not isinstance(document_id, dict) or document_id.get("@document-id-type") != "docdb":
                continue
            country = "".join(
                character
                for character in _text(document_id.get("country")).upper()
                if character.isalnum()
            )
            doc_number = "".join(
                character
                for character in _text(document_id.get("doc-number")).upper()
                if character.isalnum()
            )
            if country and doc_number:
                candidates.add(f"{country}{doc_number}")
    if len(candidates) != 1:
        return ""
    return next(iter(candidates))


def parse_family(data: dict) -> dict:
    """Parse DOCDB patent family members from an OPS response."""
    family_data = data.get("ops:world-patent-data", {}).get("ops:patent-family", {})
    members_raw = family_data.get("ops:family-member", [])
    if isinstance(members_raw, dict):
        members_raw = [members_raw]

    members: list[dict] = []
    for member in members_raw:
        if not isinstance(member, dict):
            continue
        application_number = _explicit_family_application_number(member)
        publication_reference = member.get("publication-reference", {}).get("document-id", [])
        if isinstance(publication_reference, dict):
            publication_reference = [publication_reference]
        for doc_id in publication_reference:
            if isinstance(doc_id, dict) and doc_id.get("@document-id-type") == "docdb":
                members.append(
                    {
                        "country": doc_id.get("country", {}).get("$", ""),
                        "doc_number": doc_id.get("doc-number", {}).get("$", ""),
                        "kind": doc_id.get("kind", {}).get("$", ""),
                        "application_number": application_number,
                        "application_identity_verified": bool(application_number),
                        "application_identity_source": (
                            _OPS_FAMILY_APPLICATION_IDENTITY_SOURCE if application_number else ""
                        ),
                    }
                )

    return {
        "family_id": family_data.get("@family-id", ""),
        "members": members,
    }


def parse_biblio(data: dict) -> dict:
    """Parse bibliographic data from an OPS biblio response."""
    result: dict = {}
    world_data = _first_dict(data.get("ops:world-patent-data", {}))
    exchange_docs_container = _first_dict(world_data.get("exchange-documents", {}))
    exchange_docs = _first_dict(exchange_docs_container.get("exchange-document", {}))

    biblio = exchange_docs.get("bibliographic-data", {})

    titles = biblio.get("invention-title", [])
    if isinstance(titles, dict):
        titles = [titles]
    for title in titles:
        if title.get("@lang", "") == "en" or not result.get("title"):
            result["title"] = title.get("$", "")

    abstracts = exchange_docs.get("abstract", [])
    if isinstance(abstracts, dict):
        abstracts = [abstracts]
    for abstract in abstracts:
        if abstract.get("@lang", "") == "en" or not result.get("abstract"):
            paragraph = abstract.get("p", {})
            result["abstract"] = (
                paragraph.get("$", "") if isinstance(paragraph, dict) else str(paragraph)
            )

    applicants_data = biblio.get("parties", {}).get("applicants", {}).get("applicant", [])
    if isinstance(applicants_data, dict):
        applicants_data = [applicants_data]
    result["applicants"] = []
    for applicant in applicants_data:
        name = applicant.get("applicant-name", {}).get("name", {}).get("$", "")
        if name:
            result["applicants"].append(name)

    inventors_data = biblio.get("parties", {}).get("inventors", {}).get("inventor", [])
    if isinstance(inventors_data, dict):
        inventors_data = [inventors_data]
    result["inventors"] = []
    for inventor in inventors_data:
        name = inventor.get("inventor-name", {}).get("name", {}).get("$", "")
        if name:
            result["inventors"].append(name)

    cpcs = biblio.get("patent-classifications", {}).get("patent-classification", [])
    if isinstance(cpcs, dict):
        cpcs = [cpcs]
    result["cpc_codes"] = []
    for cpc in cpcs:
        section = cpc.get("section", {}).get("$", "")
        patent_class = cpc.get("class", {}).get("$", "")
        subclass = cpc.get("subclass", {}).get("$", "")
        main_group = cpc.get("main-group", {}).get("$", "")
        subgroup = cpc.get("subgroup", {}).get("$", "")
        if section:
            code = f"{section}{patent_class}{subclass}"
            if main_group and subgroup:
                code = f"{code}{main_group}/{subgroup}"
            elif main_group:
                code = f"{code}{main_group}"
            result["cpc_codes"].append(code.strip())

    priorities = biblio.get("priority-claims", {}).get("priority-claim", [])
    if isinstance(priorities, dict):
        priorities = [priorities]
    result["priority_claims"] = []
    for priority in priorities:
        doc_id = _first_dict(priority.get("document-id", {}))
        result["priority_claims"].append(
            {
                "country": doc_id.get("country", {}).get("$", ""),
                "doc_number": doc_id.get("doc-number", {}).get("$", ""),
                "date": doc_id.get("date", {}).get("$", ""),
                "kind": priority.get("@kind", ""),
            }
        )

    return result


def parse_claims_text(data: dict) -> str:
    """Parse English claims text from an OPS fulltext response."""
    claims_data = (
        data.get("ops:world-patent-data", {})
        .get("ftxt:fulltext-documents", {})
        .get("ftxt:fulltext-document", {})
        .get("claims", [])
    )
    if isinstance(claims_data, dict):
        claims_data = [claims_data]

    for claims in claims_data:
        if claims.get("@lang", "") != "en":
            continue
        claim_list = claims.get("claim", [])
        if isinstance(claim_list, dict):
            claim_list = [claim_list]
        texts = []
        for claim in claim_list:
            text = claim.get("claim-text", {})
            if isinstance(text, dict):
                texts.append(text.get("$", ""))
            elif isinstance(text, str):
                texts.append(text)
            elif isinstance(text, list):
                texts.extend(
                    item.get("$", "") if isinstance(item, dict) else str(item) for item in text
                )
        return "\n\n".join(texts)
    return ""


def _register_documents(data: dict) -> list[dict]:
    documents = (
        data.get("ops:world-patent-data", {})
        .get("ops:register-search", {})
        .get("reg:register-documents", {})
        .get("reg:register-document", [])
    )
    return [item for item in _as_list(documents) if isinstance(item, dict)]


def _country_codes(value) -> list[str]:
    codes: list[str] = []
    for item in _as_list(value):
        code = _text(item)
        if code and code not in codes:
            codes.append(code)
    return codes


def _register_event(dossier_event: dict) -> dict:
    descriptions = [
        item for item in _as_list(dossier_event.get("reg:event-text", [])) if isinstance(item, dict)
    ]
    description = next(
        (
            _text(item)
            for item in descriptions
            if str(item.get("@event-text-type", "")).upper() == "DESCRIPTION"
        ),
        "",
    )
    if not description and descriptions:
        description = _text(descriptions[0])
    return {
        "event_date": _nested_text(
            dossier_event,
            "reg:event-date",
            "reg:date",
        ),
        "event_code": _text(dossier_event.get("reg:event-code")),
        "event_description": description,
        "country": "EP",
        "gazette_number": _nested_text(
            dossier_event,
            "reg:gazette-reference",
            "reg:gazette-num",
        ),
        "gazette_date": _nested_text(
            dossier_event,
            "reg:gazette-reference",
            "reg:date",
        ),
    }


def _procedural_step(step: dict) -> dict:
    descriptions = [
        item
        for item in _as_list(step.get("reg:procedural-step-text", []))
        if isinstance(item, dict)
    ]
    description = next(
        (
            _text(item)
            for item in descriptions
            if str(item.get("@step-text-type", "")).upper() == "STEP_DESCRIPTION"
        ),
        "",
    )
    dates = [
        item
        for item in _as_list(step.get("reg:procedural-step-date", []))
        if isinstance(item, dict)
    ]
    return {
        "step_code": _text(step.get("reg:procedural-step-code")),
        "step_description": description,
        "procedure_phase": _text(step.get("@procedure-step-phase")),
        "dates": [
            {
                "type": _text(item.get("@step-date-type")),
                "date": _text(item.get("reg:date")),
            }
            for item in dates
        ],
    }


def parse_register(data: dict, *, unitary_data: dict | None = None) -> dict:
    """Parse central EP Register data from OPS.

    This intentionally does not describe designated-state national
    enforceability.  That requires the relevant national register.
    """
    result: dict = {
        "designated_states": [],
        "status": "",
        "opposition_events": [],
        "legal_events": [],
        "procedural_steps": [],
        "lapsed_during_ep_proceedings": [],
        "record_produced_at": "",
        "unitary_patent": {},
        "scope_limitation": (
            "Central EP Register evidence does not establish national post-grant "
            "status; authoritative target-state register evidence is required."
        ),
    }
    reg_docs = _register_documents(data)
    unitary_docs = _register_documents(unitary_data or {})

    for doc in reg_docs:
        biblio = doc.get("reg:bibliographic-data", {})
        result["record_produced_at"] = _first_text(
            doc.get("@date-produced"),
            result["record_produced_at"],
        )
        designation = biblio.get(
            "reg:designation-of-states",
            biblio.get("reg:designated-states", {}),
        )
        pct = designation.get("reg:designation-pct", {}).get(
            "reg:regional",
            {},
        )
        epc = designation.get("reg:designation-epc", {})
        for state in [
            *_country_codes(pct.get("reg:country", [])),
            *_country_codes(epc.get("reg:country", [])),
        ]:
            if state not in result["designated_states"]:
                result["designated_states"].append(state)

        status = _first_text(
            doc.get("@status"),
            biblio.get("@status"),
            biblio.get("reg:status"),
        )
        if status:
            result["status"] = status

        for event in _as_list(biblio.get("reg:events", {}).get("reg:event", [])):
            if not isinstance(event, dict):
                continue
            event_data = event.get("reg:event-data", {})
            description_value = _text(event_data.get("reg:event-description"))
            description = description_value.lower()
            event_record = {
                "event_date": _text(event_data.get("reg:event-date")),
                "event_code": _text(event_data.get("reg:event-code")),
                "event_description": description_value,
                "country": _text(event_data.get("reg:event-country")) or "EP",
            }
            result["legal_events"].append(event_record)
            if "opposition" in description or "oppos" in description:
                result["opposition_events"].append(event_record)

        for event_data in _as_list(doc.get("reg:events-data", [])):
            if not isinstance(event_data, dict):
                continue
            for dossier_event in _as_list(event_data.get("reg:dossier-event", [])):
                if not isinstance(dossier_event, dict):
                    continue
                event_record = _register_event(dossier_event)
                result["legal_events"].append(event_record)
                description = event_record["event_description"].lower()
                if "opposition" in description or "oppos" in description:
                    result["opposition_events"].append(event_record)

        procedure = doc.get("reg:procedural-data", {})
        for step in _as_list(procedure.get("reg:procedural-step", [])):
            if isinstance(step, dict):
                result["procedural_steps"].append(_procedural_step(step))

        term = biblio.get("reg:term-of-grant", {})
        for lapse in _as_list(term.get("reg:lapsed-in-country", [])):
            if not isinstance(lapse, dict):
                continue
            result["lapsed_during_ep_proceedings"].append(
                {
                    "country": _text(lapse.get("reg:country")),
                    "date": _text(lapse.get("reg:date")),
                }
            )

    for doc in unitary_docs:
        unitary = doc.get("reg:unitary-patent", {})
        statuses = unitary.get("reg:unitary-patent-statuses", {}).get(
            "reg:unitary-patent-status", []
        )
        result["unitary_patent"] = {
            "statuses": [
                {
                    "status_code": _text(status.get("@status-code")),
                    "status": _text(status),
                    "change_date": _text(status.get("@change-date")),
                }
                for status in _as_list(statuses)
                if isinstance(status, dict)
            ],
            "record_produced_at": _text(doc.get("@date-produced")),
        }

    return result


def extract_drawing_page_count(data: dict) -> int:
    """Extract the available drawing page count from an OPS images response."""
    doc_instances = (
        data.get("ops:world-patent-data", {})
        .get("ops:document-inquiry", {})
        .get("ops:inquiry-result", {})
        .get("ops:document-instance", [])
    )
    if isinstance(doc_instances, dict):
        doc_instances = [doc_instances]

    for instance in doc_instances:
        desc = instance.get("@desc", "")
        if "Drawing" not in desc and "drawing" not in desc:
            continue
        try:
            return int(instance.get("@number-of-pages", "0"))
        except (TypeError, ValueError):
            return 0

    return 0
