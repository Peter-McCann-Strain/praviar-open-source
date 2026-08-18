// Canonical blocker-family docket.
// A family is a navigation context, never the right on which exposure rests.

#import "../lib/colors.typ": accent, border, ink, muted, risk-high, risk-high-bg, risk-high-text, surface
#import "../lib/typography.typ": font-mono

#let _posture(value) = upper(str(value).replace("_", " "))

#let render-blocker-families(data) = {
  let decision = data.at("clearance_decision", default: (:))
  let audit = decision.at("decision_audit", default: (:))
  let families = audit.at("blocker_families", default: ())

  if families.len() == 0 { return }

  heading(level: 1)[National-right blocker docket]

  block(
    width: 100%,
    fill: risk-high-bg,
    stroke: 0.75pt + risk-high,
    radius: 5pt,
    inset: 11pt,
  )[
    #set text(size: 9pt, fill: risk-high-text)
    *Reliance boundary.* Family records group related publications for
    navigation. A record may cite publications, including an international
    application, as evidence. Enforceability attaches only to an identified
    in-force national or regional right and its exact claims, never to a WO
    publication or patent-family label. Ownership and patent term are not
    inferred here; counsel must confirm both.
  ]

  v(0.55em)

  for (family-index, family) in families.enumerate() {
    let family-id = family.at("family_id", default: "Not reported")
    let blocker-id = family.at("blocker_id", default: "Not reported")
    let primary-id = family.at("primary_blocking_patent_id", default: "Not reported")
    let material-ids = family.at("material_family_patent_ids", default: ())
    let blocking-ids = family.at("blocking_patent_ids", default: ())
    let jurisdictions = family.at("jurisdictions", default: ())
    let claims = family.at("blocking_claims", default: ())

    block(
      width: 100%,
      fill: surface,
      stroke: 0.5pt + border,
      radius: 5pt,
      inset: 11pt,
      breakable: claims.len() > 3,
    )[
      #text(size: 8pt, weight: "bold", fill: accent)[BLOCKER FAMILY #(family-index + 1)]
      #v(0.15em)
      #text(size: 12pt, weight: "bold", fill: ink)[Primary docket reference: #primary-id]
      #v(0.3em)

      #table(
        columns: (1.1fr, 1.9fr),
        inset: 4pt,
        stroke: 0.5pt + border,
        [*Family context*], text(font: font-mono, size: 7.5pt)[#family-id],
        [*Governed blocker ID*], text(font: font-mono, size: 7.5pt)[#blocker-id],
        [*Jurisdictions*], if jurisdictions.len() > 0 { jurisdictions.map(str).join(", ") } else { "Not reported" },
        [*Blocking right / publication IDs*], if blocking-ids.len() > 0 { blocking-ids.map(str).join(", ") } else { "Not reported" },
        [*Material publications*], [#material-ids.len() publication#if material-ids.len() != 1 [s]],
      )

      #if material-ids.len() > 0 {
        v(0.25em)
        text(size: 7.5pt, fill: muted)[
          Material family publications: #material-ids.map(str).join(", ")
        ]
      }

      #v(0.45em)
      #text(size: 10pt, weight: "bold", fill: ink)[Exact blocking claims]
      #v(0.2em)

      #if claims.len() == 0 {
        block(
          fill: risk-high-bg,
          stroke: 0.5pt + risk-high,
          inset: 8pt,
        )[
          No exact blocking-claim record is attached. Do not rely on the family
          record as a clearance blocker.
        ]
      } else {
        for claim in claims {
          let patent-id = claim.at("patent_id", default: "Not reported")
          let claim-number = claim.at("claim_number", default: "Not reported")
          let claim-jurisdiction = claim.at("jurisdiction", default: "Not reported")
          let literal-risk = claim.at("literal_risk", default: "not_assessed")
          let doe-risk = claim.at("doe_risk", default: "not_assessed")
          let invalidity = claim.at("invalidity_strength", default: "")
          let invalidity-label = if invalidity == "" { "NOT ASSESSED" } else { _posture(invalidity) }
          let legal-status = claim.at("legal_status", default: "Not reported")
          let accused-acts = claim.at("accused_acts", default: ())
          let record-basis = claim.at("record_basis", default: ())

          block(
            width: 100%,
            inset: (left: 8pt, y: 6pt),
            stroke: (left: 2.5pt + risk-high),
            breakable: true,
          )[
            #text(font: font-mono, size: 8.5pt, weight: "bold")[
              #patent-id / claim #claim-number / #claim-jurisdiction
            ]
            #v(0.15em)
            #text(size: 8.5pt)[
              Literal: *#_posture(literal-risk)*; equivalents:
              *#_posture(doe-risk)*; invalidity:
              *#invalidity-label*;
              status: *#upper(str(legal-status))*.
            ]
            #v(0.12em)
            #text(size: 8pt, fill: muted)[
              Accused acts: #if accused-acts.len() > 0 { accused-acts.map(str).join(", ") } else { "Not reported" }.
              Record basis: #if record-basis.len() > 0 { record-basis.map(str).join(", ") } else { "Not reported" }.
            ]
          ]
        }
      }
    ]
    v(0.45em)
  }
}
