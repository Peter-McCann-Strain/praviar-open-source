// Praviar Reusable Claim Chart Table
// Renders claim elements with status coloring: Element | Analysis | Status.
//
// Usage: #import "claim-chart.typ": render-claim-chart
//        #render-claim-chart(elements)

#import "../lib/colors.typ": ink, border, muted, surface, element-status-color
#import "../lib/typography.typ": font-table, font-mono

// ── Status Badge (inline) ──────────────────────────────────────────────────

#let element-badge(status) = {
  let s = lower(str(status))
  let label = if s == "met" { "MET" }
    else if s == "partially_met" or s == "partial" { "PARTIAL" }
    else if s == "not_met" { "NOT MET" }
    else { "UNCLEAR" }

  let icon = if s == "met" { "\u{25B2}" }           // Triangle up (risk)
    else if s == "partially_met" or s == "partial" { "\u{25C6}" }  // Diamond
    else if s == "not_met" { "\u{2714}" }            // Check (safe)
    else { "\u{25CF}" }                               // Circle

  let color = element-status-color(status)

  box(
    fill: color.lighten(85%),
    stroke: 0.5pt + color,
    radius: 2pt,
    inset: (x: 4pt, y: 2pt),
  )[
    #set text(size: 7pt, weight: "bold", fill: color)
    #icon #label
  ]
}

// ── Claim Chart Table ──────────────────────────────────────────────────────
// elements: array of dicts with keys:
//   element_number, element_text, status, reasoning, confidence

#let render-claim-chart(elements) = {
  if elements.len() == 0 {
    text(size: 9pt, fill: muted)[_No claim elements to display._]
    return
  }

  table(
    columns: (auto, 2fr, 2fr, auto),
    align: (center, left, left, center),
    stroke: 0.5pt + border,
    inset: 5pt,
    // Header
    table.header(
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[No.]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Claim Element]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Analysis]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Status]],
    ),
    // Rows
    ..for (idx, elem) in elements.enumerate() {
      let num = elem.at("element_number", default: idx + 1)
      let text-content = elem.at("element_text", default: "")
      let reasoning = elem.at("reasoning", default: "")
      let status = elem.at("status", default: "unclear")
      let confidence = elem.at("confidence", default: none)

      // Tint row background by status
      let status-tint = element-status-color(status).lighten(92%)

      (
        table.cell(fill: status-tint)[#text(size: 8pt, weight: "bold")[#num]],
        table.cell(fill: status-tint)[
          #set text(size: 8pt)
          #text-content
        ],
        table.cell(fill: status-tint)[
          #set text(size: 8pt)
          #reasoning
          #if confidence != none {
            v(0.15em)
            text(size: 7pt, fill: muted)[Confidence: #str(calc.round(float(confidence) * 100, digits: 0))%]
          }
        ],
        table.cell(fill: status-tint)[#element-badge(status)],
      )
    }
  )
}
