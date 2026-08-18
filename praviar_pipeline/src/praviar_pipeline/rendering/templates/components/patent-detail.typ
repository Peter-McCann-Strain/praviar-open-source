// Praviar Patent Detail Section
// Renders full analysis for a single HIGH or MEDIUM risk patent.

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface, accent, risk-high, risk-low, risk-moderate, risk-high-bg, risk-moderate-bg, risk-moderate-text, risk-clear-bg, risk-clear-text, risk-bg-color, risk-text-color
#import "../lib/typography.typ": font-heading, font-body, font-mono, font-table
#import "../lib/risk-badge.typ": risk-badge
#import "../lib/utils.typ": fmt-date-short, truncate, risk-order
#import "claim-chart.typ": render-claim-chart

// ── Internal Helpers ───────────────────────────────────────────────────────

#let _bool_badge(value) = {
  if value == none {
    text(fill: risk-moderate, weight: "bold", size: 8pt)[UNRESOLVED]
  } else if value {
    text(fill: risk-high, weight: "bold", size: 8pt)[YES]
  } else {
    text(fill: risk-low, weight: "bold", size: 8pt)[NO]
  }
}

#let _score_cell(score) = {
  let s = float(score)
  let color = if s >= 0.7 { risk-low }
    else if s >= 0.4 { risk-moderate }
    else { risk-high }
  text(size: 8pt, weight: "bold", fill: color)[#str(calc.round(s * 100, digits: 0))%]
}

#let _include_section(export-options, section-id) = {
  export-options.at("sections", default: ()).contains(section-id)
}

// ── Single Patent Detail ───────────────────────────────────────────────────

#let _render_single_patent(patent, narratives, doe-list, invalidity-list, assets-dir, export-options) = {
  let pid = patent.at("patent_id", default: "N/A")
  let title = patent.at("title", default: "Untitled")
  let assignee = patent.at("assignee", default: "Unknown")
  let risk-level = patent.at("risk_level", default: "medium")
  let expiry = patent.at("expiry_date", default: none)
  let risk-summary-text = patent.at("risk_summary", default: "")
  let claims = patent.at("claims_analyzed", default: ())
  let ob-info = patent.at("orange_book_info", default: none)
  let design-arounds = patent.at("design_around_suggestions", default: ())

  // ── Section Header ───────────────────────────────────────────────────
  heading(level: 2)[#pid: #truncate(title, 60)]

  // ── Metadata Box ─────────────────────────────────────────────────────
  block(
    width: 100%,
    fill: surface,
    stroke: 0.5pt + border,
    radius: 4pt,
    inset: 10pt,
  )[
    #grid(
      columns: (1fr, 1fr),
      column-gutter: 12pt,
      row-gutter: 0.35em,
      [*Patent ID:*], text(font: font-mono, size: 9pt)[#pid],
      [*Title:*], text(size: 9pt)[#title],
      [*Assignee:*], text(size: 9pt)[#assignee],
      [*Risk Level:*], risk-badge(risk-level),
      [*Expiry Date:*], if expiry != none { fmt-date-short(expiry) } else { "N/A" },
      [*Orange Book:*], if ob-info != none {
        let ob-str = if type(ob-info) == str { ob-info }
          else if type(ob-info) == dictionary { ob-info.at("listing_type", default: "Listed") }
          else { "Listed" }
        text(fill: risk-high, weight: "bold")[#ob-str]
      } else { text(fill: muted)[Not listed] },
    )
  ]
  v(0.4em)

  // ── Risk Summary ─────────────────────────────────────────────────────
  if risk-summary-text != "" and risk-summary-text != none {
    heading(level: 3)[Risk Assessment]
    block(
      width: 100%,
      fill: risk-bg-color(risk-level).lighten(40%),
      radius: 3pt,
      inset: 10pt,
      stroke: 0.5pt + risk-text-color(risk-level).lighten(50%),
    )[
      #set text(size: 9.5pt)
      #risk-summary-text
    ]
    v(0.3em)
  }

  // ── Narrative ────────────────────────────────────────────────────────
  {
    let narrative = narratives.at(pid, default: none)
    if narrative != none and narrative != "" {
      heading(level: 3)[Analysis Narrative]
      set text(size: 9.5pt)
      set par(justify: true)
      narrative
      v(0.3em)
    }
  }

  // ── Claim Charts ─────────────────────────────────────────────────────
  if claims.len() > 0 and _include_section(export-options, "claim_charts") {
    heading(level: 3)[Claim Analysis]

    for claim in claims {
      let claim-num = claim.at("claim_number", default: "?")
      let claim-type = claim.at("claim_type", default: "")
      let overall-status = claim.at("overall_status", default: "unclear")
      let overall-conf = claim.at("overall_confidence", default: none)
      let elements = claim.at("elements", default: ())

      heading(level: 4)[Claim #claim-num #if claim-type != "" { [(#claim-type)] }]

      // Overall claim verdict
      {
        let status-label = if lower(str(overall-status)) == "met" { "All Elements Met" }
          else if lower(str(overall-status)) == "partially_met" { "Partially Met" }
          else if lower(str(overall-status)) == "not_met" { "Not Met" }
          else { "Inconclusive" }

        text(size: 9pt)[*Overall:* #status-label]
        if overall-conf != none {
          text(size: 9pt)[ (confidence: #str(calc.round(float(overall-conf) * 100, digits: 0))%)]
        }
        v(0.2em)
      }

      // Element-by-element chart
      render-claim-chart(elements)
      v(0.3em)
    }
  }

  // ── Structure Comparison Image ───────────────────────────────────────
  {
    let has-comparison = patent.at("_has_comparison_image", default: false)
    if has-comparison {
      heading(level: 3)[Structure Comparison]
      let comparison-id = patent.at("_comparison_image_id", default: pid)
      let comparison-ext = patent.at("_comparison_image_ext", default: "png")
      let img-path = assets-dir + "/comparison_" + comparison-id + "." + comparison-ext
      align(center)[
        #image(
          img-path,
          width: 4.5in,
          alt: "Structural comparison between the target compound and " + pid,
        )
      ]
      align(center)[
        #set text(size: 8pt, fill: muted)
        _Figure: Structural comparison between target compound and patent claims._
      ]
      v(0.3em)
    }
  }

  // ── Doctrine of Equivalents ──────────────────────────────────────────
  {
    let doe = doe-list.filter(d => d.at("patent_id", default: "") == pid)
    if doe.len() > 0 {
      heading(level: 3)[Doctrine of Equivalents]

      for assessment in doe {
        let claim-num = assessment.at("claim_number", default: "?")
        let elem-num = assessment.at("element_number", default: "?")
        let equivalent = assessment.at("overall_equivalent", default: none)
        let confidence = assessment.at("confidence_band", default: "")
        let reasoning = assessment.at("reasoning", default: "")
        let estoppel = assessment.at("estoppel", default: (:))
        let fwr = assessment.at("fwr", default: (:))

        text(size: 9pt, weight: "bold")[Claim #claim-num, Element #elem-num]
        v(0.15em)

        // FWR Analysis
        if fwr.keys().len() > 0 {
          table(
            columns: (1fr, auto),
            align: (left, center),
            stroke: 0.5pt + border,
            inset: 5pt,
            fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
            table.header(
              table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[FWR Test]],
              table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Result]],
            ),
            [Same Function], _bool_badge(fwr.at("same_function", default: none)),
            [Same Way], _bool_badge(fwr.at("same_way", default: none)),
            [Same Result], _bool_badge(fwr.at("same_result", default: none)),
            [*Overall Equivalent*], _bool_badge(equivalent),
          )
          v(0.2em)
        }

        // Estoppel
        if estoppel.keys().len() > 0 {
          let applies = estoppel.at("estoppel_applies", default: false)
          let scope = estoppel.at("surrendered_scope", default: "")
          if applies {
            block(
              width: 100%,
              fill: risk-moderate-bg,
              stroke: 0.5pt + risk-moderate,
              radius: 3pt,
              inset: 8pt,
            )[
              #set text(size: 9pt)
              #text(weight: "bold", fill: risk-moderate-text)[\u{26A0} Prosecution History Estoppel Applies]
              #if scope != "" {
                v(0.15em)
                text(size: 8.5pt)[Surrendered scope: #scope]
              }
            ]
            v(0.2em)
          }
        }

        if reasoning != "" {
          text(size: 9pt)[#reasoning]
          v(0.2em)
        }

        if confidence != "" {
          text(size: 8.5pt, fill: muted)[Confidence band: #confidence]
          v(0.3em)
        }
      }
    }
  }

  // ── Invalidity Assessment ────────────────────────────────────────────
  {
    let inv = invalidity-list.filter(i => i.at("patent_id", default: "") == pid)
    if inv.len() > 0 and _include_section(export-options, "invalidity_assessment") {
      heading(level: 3)[Invalidity Assessment]

      for assessment in inv {
        let strength = assessment.at("overall_invalidity_strength", default: "weak")
        let inv-reasoning = assessment.at("reasoning", default: "")
        let claim-charts = assessment.at("claim_charts", default: ())
        let prior-art = assessment.at("prior_art", default: ())
        let graham = assessment.at("graham_factors", default: none)
        let enablement = assessment.at("enablement_screening", default: none)
        let ptab = assessment.at("ptab", default: (:))

        // Strength badge
        {
          let strength-color = if lower(str(strength)) == "strong" { risk-low }
            else if lower(str(strength)) == "moderate" { risk-moderate }
            else { risk-high }
          text(size: 10pt)[*Invalidity Strength:* ]
          box(
            fill: strength-color.lighten(85%),
            stroke: 0.5pt + strength-color,
            radius: 3pt,
            inset: (x: 6pt, y: 3pt),
          )[
            #set text(size: 8pt, weight: "bold", fill: strength-color)
            #upper(str(strength))
          ]
          v(0.3em)
        }

        if inv-reasoning != "" {
          text(size: 9.5pt)[#inv-reasoning]
          v(0.3em)
        }

        // Prior Art References
        if prior-art.len() > 0 {
          text(size: 9.5pt, weight: "bold")[Prior Art References]
          v(0.15em)

          table(
            columns: (auto, 2fr, auto, auto),
            align: (left, left, center, center),
            stroke: 0.5pt + border,
            inset: 5pt,
            fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
            table.header(
              table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Ref ID]],
              table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Title]],
              table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Anticipation]],
              table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Obviousness]],
            ),
            ..for ref in prior-art {
              let ref-id = ref.at("reference_id", default: "N/A")
              let ref-title = ref.at("title", default: "")
              let antic = ref.at("anticipation_score", default: 0)
              let obv = ref.at("obviousness_score", default: 0)
              (
                text(font: font-mono, size: 7.5pt)[#ref-id],
                text(size: 8pt)[#truncate(ref-title, 50)],
                _score_cell(antic),
                _score_cell(obv),
              )
            }
          )
          v(0.2em)
        }

        // Graham Factors
        if graham != none and type(graham) == dictionary {
          text(size: 9.5pt, weight: "bold")[Graham Factors]
          v(0.15em)
          for (factor, value) in graham.pairs() {
            text(size: 9pt)[*#factor:* #str(value)]
            linebreak()
          }
          v(0.2em)
        } else if graham != none and type(graham) == str {
          text(size: 9.5pt, weight: "bold")[Graham Factors]
          v(0.15em)
          text(size: 9pt)[#graham]
          v(0.2em)
        }

        // PTAB
        if ptab.keys().len() > 0 {
          let challenged = ptab.at("has_been_challenged", default: false)
          let proceedings = ptab.at("proceedings", default: ())
          if challenged {
            block(
              width: 100%,
              fill: risk-clear-bg,
              stroke: 0.5pt + risk-clear-text,
              radius: 3pt,
              inset: 8pt,
            )[
              #set text(size: 9pt)
              #text(weight: "bold", fill: risk-clear-text)[PTAB Challenge History]
              #if type(proceedings) == array and proceedings.len() > 0 {
                v(0.15em)
                for p in proceedings {
                  let num = p.at("proceeding_number", default: "")
                  let ptype = p.at("type", default: "")
                  let pstatus = p.at("status", default: "")
                  [- #num (#ptype): #pstatus]
                }
              }
            ]
            v(0.2em)
          }
        }
      }
    }
  }

  // ── Design-Around Suggestions ────────────────────────────────────────
  if design-arounds.len() > 0 and _include_section(export-options, "patent_analysis") {
    heading(level: 3)[Design-Around Suggestions]

    for (idx, suggestion) in design-arounds.enumerate() {
      let desc = if type(suggestion) == str { suggestion }
        else if type(suggestion) == dictionary {
          suggestion.at("suggestion", default: "Description not reported")
        }
        else { str(suggestion) }
      let feasibility = if type(suggestion) == dictionary { suggestion.at("feasibility", default: none) } else { none }

      block(
        width: 100%,
        fill: risk-clear-bg,
        stroke: 0.5pt + border,
        radius: 3pt,
        inset: 8pt,
      )[
        #text(weight: "bold", fill: accent)[#(idx + 1).] #desc
        #if feasibility != none {
          h(1em)
          text(size: 8pt, fill: muted)[(Feasibility: #str(feasibility))]
        }
      ]
      v(0.15em)
    }
    v(0.2em)
  }

  // Visual separator between patents
  v(0.3em)
  line(length: 100%, stroke: 0.5pt + border)
  v(0.3em)
}

// ── Render All High/Medium Patents ─────────────────────────────────────────

#let render-patent-details(data, assets-dir, export-options) = {
  let analyses = data.at("patent_analyses", default: ())
  let narratives = data.at("patent_narratives", default: (:))
  let doe-list = data.at("doe_assessments", default: ())
  let invalidity-list = data.at("invalidity_assessments", default: ())

  // Filter to HIGH and MEDIUM only
  let detailed = analyses.filter(a => {
    let rl = lower(str(a.at("risk_level", default: "")))
    rl == "high" or rl == "medium" or rl == "moderate"
  })

  // Sort: HIGH first
  let sorted = detailed.sorted(key: a => risk-order(a.at("risk_level", default: "clear")))

  if sorted.len() == 0 { return }

  pagebreak()
  heading(level: 1)[Detailed Patent Analysis]

  for patent in sorted {
    _render_single_patent(patent, narratives, doe-list, invalidity-list, assets-dir, export-options)
  }
}
