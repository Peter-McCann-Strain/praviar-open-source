// Praviar Pipeline Executive Summary

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface, accent, risk-bg-color, risk-text-color, risk-moderate-bg, risk-moderate, risk-moderate-text
#import "../lib/typography.typ": font-heading, font-body
#import "../lib/risk-badge.typ": risk-badge
#import "../lib/utils.typ": get, fmt-number

#let render-executive(data, assets-dir) = {
  let risk = data.at("risk_summary", default: (:))
  let overall = data.at("_governed_risk_level", default: "unknown")
  let decision = data.at("clearance_decision", default: (:)).at("decision", default: "unclear")
  let blocking = risk.at("blocking_patents_count", default: 0)
  let total-analyzed = risk.at("total_patents_analyzed", default: 0)
  let key-risks = risk.at("key_risks", default: ())
  let summary-text = risk.at("executive_summary", default: "")

  heading(level: 1)[Executive Summary]

  // ── Risk Verdict Box ───────────────────────────────────────────────────
  block(
    width: 100%,
    fill: risk-bg-color(overall),
    stroke: 1pt + risk-text-color(overall).lighten(30%),
    radius: 6pt,
    inset: 16pt,
  )[
    #grid(
      columns: (auto, 1fr),
      column-gutter: 16pt,
      align: (center + horizon, left),
      // Left: large badge
      risk-badge(overall, large: true),
      // Right: summary metrics
      [
        #set text(font: font-heading, size: 12pt, weight: "bold", fill: risk-text-color(overall))
        Clearance Decision: #upper(str(decision)) (#upper(str(overall)) risk)

        #set text(font: font-body, size: 10pt, weight: "regular", fill: risk-text-color(overall))
        #fmt-number(blocking) blocking patent#if blocking != 1 [s] identified out of #fmt-number(total-analyzed) analyzed
      ],
    )
  ]

  v(0.6em)

  // ── Risk Gauge Chart (if available) ────────────────────────────────────
  {
    let has-gauge = data.at("_has_risk_gauge", default: false)
    if has-gauge {
      align(center)[
        #image(
          assets-dir + "/risk_gauge.png",
          width: 3in,
          alt: "Risk gauge showing " + upper(str(overall)) + " risk",
        )
      ]
      v(0.4em)
    }
  }

  // ── Key Risks ──────────────────────────────────────────────────────────
  if key-risks.len() > 0 {
    text(font: font-heading, size: 11pt, weight: "bold", fill: ink)[Key Risks]
    v(0.3em)

    for (idx, risk-item) in key-risks.enumerate() {
      block(
        width: 100%,
        inset: (left: 8pt, y: 3pt),
      )[
        #text(font: font-heading, weight: "bold", fill: accent)[#(idx + 1).] #risk-item
      ]
    }
    v(0.4em)
  }

  // ── Executive Summary Text ─────────────────────────────────────────────
  if summary-text != "" {
    text(font: font-heading, size: 11pt, weight: "bold", fill: ink)[Analysis Summary]
    v(0.3em)
    block(
      width: 100%,
      fill: surface,
      radius: 4pt,
      inset: 12pt,
      stroke: 0.5pt + border,
    )[
      #set text(size: 10pt)
      #set par(justify: true)
      #summary-text
    ]
    v(0.4em)
  }

  // ── Confidence Assessment ──────────────────────────────────────────────
  {
    let validation-issues = risk.at("summary_validation_issues", default: ())
    if validation-issues.len() > 0 {
      block(
        width: 100%,
        fill: risk-moderate-bg,
        radius: 4pt,
        inset: 10pt,
        stroke: 0.5pt + risk-moderate,
      )[
        #set text(size: 9pt)
        #text(weight: "bold", fill: risk-moderate-text)[\u{26A0} Confidence Notes]
        #v(0.2em)
        #for issue in validation-issues [
          - #issue
        ]
      ]
    }
  }
}
