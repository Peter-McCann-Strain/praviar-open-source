// Drawing analysis section — chemical structures extracted from patent drawings
#import "../lib/colors.typ"
#import "../lib/risk-badge.typ": risk-badge

#let _same-governance-identity(left, right) = {
  let checks = (
    left.at("schema_version", default: "") == right.at("schema_version", default: ""),
    left.at("rollout_state", default: "") == right.at("rollout_state", default: ""),
    left.at("influence_permitted", default: false) == right.at("influence_permitted", default: false),
    left.at("evidence_gate_passed", default: false) == right.at("evidence_gate_passed", default: false),
    left.at("runtime_roster_sha256", default: "") == right.at("runtime_roster_sha256", default: ""),
    left.at("ml_bom_sha256", default: "") == right.at("ml_bom_sha256", default: ""),
    left.at("calibration_artifact_id", default: "") == right.at("calibration_artifact_id", default: ""),
    left.at("calibration_artifact_revision", default: 0) == right.at("calibration_artifact_revision", default: 0),
    left.at("calibration_artifact_sha256", default: "") == right.at("calibration_artifact_sha256", default: ""),
    left.at("worker_image_digest", default: "") == right.at("worker_image_digest", default: ""),
    left.at("jurisdictions", default: ()) == right.at("jurisdictions", default: ()),
    left.at("verified_at", default: none) == right.at("verified_at", default: none),
  )
  checks.all(value => value)
}

#let _drawing-governance-panel(patents-with-structures) = {
  let provenances = patents-with-structures.map(
    drawing => drawing.at("governance_provenance", default: none)
  )
  let missing-count = provenances.filter(provenance => provenance == none).len()

  if missing-count > 0 {
    block(
      width: 100%,
      fill: colors.risk-high-bg,
      stroke: 0.75pt + colors.risk-high,
      radius: 5pt,
      inset: 11pt,
    )[
      #text(weight: "bold", fill: colors.risk-high-text)[RELIANCE BLOCKED - GOVERNANCE PROVENANCE MISSING]
      #v(0.2em)
      #text(size: 9pt)[
        #missing-count patent drawing record#if missing-count != 1 [s] are not
        bound to a rollout, evidence gate, calibration, and runtime identity.
        Do not rely on or export these drawing extracts as decision evidence.
      ]
    ]
    return
  }

  let reference = provenances.first()
  let mixed-count = provenances.filter(
    provenance => not _same-governance-identity(reference, provenance)
  ).len()

  if mixed-count > 0 {
    block(
      width: 100%,
      fill: colors.risk-high-bg,
      stroke: 0.75pt + colors.risk-high,
      radius: 5pt,
      inset: 11pt,
    )[
      #text(weight: "bold", fill: colors.risk-high-text)[RELIANCE BLOCKED - MIXED DRAWING EVIDENCE IDENTITIES]
      #v(0.2em)
      #text(size: 9pt)[
        The displayed extracts were produced under different governance or
        runtime identities. Re-run them as one governed evidence set before
        review or export.
      ]
    ]
    return
  }

  let rollout = reference.at("rollout_state", default: "")
  let influence = reference.at("influence_permitted", default: false)
  let gate = reference.at("evidence_gate_passed", default: false)
  let roster = reference.at("runtime_roster_sha256", default: "")
  let ml-bom = reference.at("ml_bom_sha256", default: "")
  let calibration-id = reference.at("calibration_artifact_id", default: "")
  let calibration-revision = reference.at("calibration_artifact_revision", default: 0)
  let calibration-hash = reference.at("calibration_artifact_sha256", default: "")
  let worker = reference.at("worker_image_digest", default: "")
  let jurisdictions = reference.at("jurisdictions", default: ())
  let verified-at = reference.at("verified_at", default: none)
  let shadow = (rollout == "internal" or rollout == "shadow") and not influence and not gate
  let live-checks = (
    rollout == "beta" or rollout == "production",
    influence,
    gate,
    roster.len() == 64,
    ml-bom.len() == 64,
    calibration-id != "",
    calibration-revision > 0,
    calibration-hash.len() == 64,
    worker.starts-with("sha256:"),
    worker.len() == 71,
    jurisdictions.len() > 0,
    verified-at != none,
  )
  let live = live-checks.all(value => value)

  if shadow {
    block(
      width: 100%,
      fill: colors.risk-moderate-bg,
      stroke: 0.75pt + colors.risk-moderate,
      radius: 5pt,
      inset: 11pt,
    )[
      #text(weight: "bold", fill: colors.risk-moderate-text)[SHADOW EVIDENCE - NON-INFLUENTIAL]
      #v(0.2em)
      #text(size: 9pt)[
        These extracts are visible for evaluation only. They did not affect
        claims, risk, or the clearance outcome and must not be presented as
        production decision evidence.
      ]
      #v(0.2em)
      #text(size: 8pt, fill: colors.muted)[Rollout: #upper(rollout); influence permitted: NO; evidence gate passed: NO.]
    ]
  } else if live {
    block(
      width: 100%,
      fill: colors.risk-clear-bg,
      stroke: 0.75pt + colors.risk-clear-text,
      radius: 5pt,
      inset: 11pt,
    )[
      #text(weight: "bold", fill: colors.risk-clear-text)[GOVERNED LIVE DRAWING EVIDENCE]
      #v(0.2em)
      #text(size: 9pt)[
        These extracts are bound to a verified release roster, ML bill of
        materials, calibration artifact, jurisdiction scope, and immutable
        worker image.
      ]
      #v(0.3em)
      #table(
        columns: (1fr, 2fr),
        inset: 3pt,
        stroke: 0.5pt + colors.border,
        [*Rollout / jurisdictions*], [#upper(rollout) / #jurisdictions.map(str).join(", ")],
        [*Calibration*], [#calibration-id / revision #calibration-revision],
        [*Verified at*], [#str(verified-at)],
        [*Runtime roster SHA-256*], [#roster],
        [*ML-BOM SHA-256*], [#ml-bom],
        [*Calibration SHA-256*], [#calibration-hash],
        [*Worker image*], [#worker],
      )
    ]
  } else {
    block(
      width: 100%,
      fill: colors.risk-high-bg,
      stroke: 0.75pt + colors.risk-high,
      radius: 5pt,
      inset: 11pt,
    )[
      #text(weight: "bold", fill: colors.risk-high-text)[RELIANCE BLOCKED - LIVE EVIDENCE BINDINGS INCOMPLETE]
      #v(0.2em)
      #text(size: 9pt)[
        This record does not satisfy either the non-influential shadow contract
        or the complete governed-live contract. Do not rely on or export these
        drawing extracts as decision evidence.
      ]
    ]
  }
}

#let render-drawings(data, assets-dir) = {
  let drawings = data.at("drawing_analyses", default: ())
  let summary = data.at("drawing_summary", default: (:))

  if drawings.len() == 0 { return }

  let patents-with-structures = drawings.filter(d => d.at("structures_found", default: 0) > 0)
  if patents-with-structures.len() == 0 { return }

  pagebreak()
  heading(level: 1)[Chemical Structure Analysis]

  // A drawing can be visually persuasive even when it was non-influential or
  // lacks production bindings. Put the reliance boundary before all results.
  _drawing-governance-panel(patents-with-structures)
  v(0.5em)

  // Summary paragraph
  let n-analyzed = summary.at("patents_analyzed", default: 0)
  let n-with = summary.at("patents_with_structures", default: 0)
  let n-total = summary.at("total_structures", default: 0)
  let n-high = summary.at("patents_with_high_risk", default: 0)

  par[
    Analyzed #n-analyzed patents for chemical structures in patent drawings.
    Extracted structures from #n-with patents (#n-total total structures).
    #if n-high > 0 [
      *#n-high patents* contain structures with HIGH similarity to the target compound.
    ]
  ]

  v(0.5em)

  // Tanimoto summary table
  let sorted-patents = patents-with-structures.sorted(key: d => -d.at("highest_tanimoto", default: 0))

  table(
    columns: (auto, auto, auto, auto),
    align: (left, center, center, center),
    stroke: 0.5pt + colors.border,
    fill: (_, y) => if y == 0 { colors.surface } else { none },
    [*Patent ID*], [*Structures*], [*Highest Tanimoto*], [*Risk Signal*],
    ..sorted-patents.map(pa => {
      let risk = upper(pa.at("highest_risk_signal", default: "none"))
      let tc = pa.at("highest_tanimoto", default: 0)
      (
        pa.patent_id,
        str(pa.at("structures_found", default: 0)),
        [#calc.round(tc, digits: 3)],
        risk-badge(risk),
      )
    }).flatten()
  )

  v(1em)

  // High-risk structure details
  let high-risk = patents-with-structures.filter(pa =>
    pa.at("highest_risk_signal", default: "none") == "high"
  )

  if high-risk.len() > 0 {
    heading(level: 2)[High-Similarity Structures]

    for pa in high-risk {
      let structures = pa.at("structures", default: ())
      let high-structs = structures.filter(s => s.at("tanimoto_to_target", default: 0) >= 0.7)

      for s in high-structs {
        let tc = calc.round(s.at("tanimoto_to_target", default: 0), digits: 3)
        let conf = calc.round(s.at("confidence", default: 0), digits: 2)
        let smiles = s.at("canonical_smiles", default: "")
        let page = s.at("page_number", default: 0)

        block(
          width: 100%,
          inset: 8pt,
          stroke: 0.5pt + colors.border,
          radius: 4pt,
        )[
          *#pa.patent_id* -- Page #page \
          SMILES: `#smiles` \
          Tanimoto: *#tc* | Confidence: #conf
          #if s.at("is_substructure_of_target", default: false) [
            | Target is substructure
          ]
        ]
        v(0.5em)
      }
    }
  }

  // Confidence disclaimer
  let low-conf-count = patents-with-structures.map(pa =>
    pa.at("structures", default: ()).filter(s => s.at("confidence", default: 1) < 0.8).len()
  ).sum()

  if low-conf-count > 0 {
    v(0.5em)
    block(
      width: 100%,
      inset: 8pt,
      fill: colors.risk-moderate-bg,
      radius: 4pt,
    )[
      *Note:* #low-conf-count structures were extracted with moderate confidence below 0.8.
      These should be verified by a qualified chemist before relying on them as evidence.
    ]
  }
}
