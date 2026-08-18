// Praviar Pipeline Risk Matrix — Color-Coded Patent Summary Table
// Sorted by risk level (HIGH first), with alternating row backgrounds.

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface, risk-bg-color
#import "../lib/typography.typ": font-heading, font-table, font-mono
#import "../lib/risk-badge.typ": risk-badge
#import "../lib/utils.typ": truncate, fmt-date-short, risk-order

#let render-risk-matrix(data) = {
  let analyses = data.at("patent_analyses", default: ())

  heading(level: 1)[Risk Matrix]

  if analyses.len() == 0 {
    block(
      width: 100%,
      fill: surface,
      radius: 4pt,
      inset: 12pt,
      stroke: 0.5pt + border,
    )[
      #set text(fill: muted)
      No patents were analyzed in this report.
    ]
    return
  }

  // ── Sort by Risk Level ─────────────────────────────────────────────────
  let sorted = analyses.sorted(key: a => risk-order(a.at("risk_level", default: "clear")))

  // ── Matrix Table ───────────────────────────────────────────────────────
  table(
    columns: (auto, 2fr, 1fr, auto, auto, auto, auto),
    align: (left, left, left, center, center, center, center),
    stroke: 0.5pt + border,
    inset: 5pt,
    // Header
    table.header(
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Patent ID]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Title]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Assignee]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Risk]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Expiry]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Claims]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[OB]],
    ),
    // Data rows
    ..for (idx, patent) in sorted.enumerate() {
      let pid = patent.at("patent_id", default: "N/A")
      let title = patent.at("title", default: "Untitled")
      let assignee = patent.at("assignee", default: "Unknown")
      let risk-level = patent.at("risk_level", default: "clear")
      let expiry = patent.at("expiry_date", default: none)
      let claims = patent.at("claims_analyzed", default: ())
      let ob = patent.at("orange_book_info", default: none)
      let bg = if calc.rem(idx, 2) == 0 { risk-bg-color(risk-level).lighten(60%) } else { surface }

      (
        table.cell(fill: bg)[#text(font: font-mono, size: 7.5pt)[#pid]],
        table.cell(fill: bg)[#text(size: 8pt)[#truncate(title, 50)]],
        table.cell(fill: bg)[#text(size: 8pt)[#truncate(assignee, 30)]],
        table.cell(fill: bg)[#risk-badge(risk-level)],
        table.cell(fill: bg)[#text(size: 8pt)[#if expiry != none { fmt-date-short(expiry) } else { "N/A" }]],
        table.cell(fill: bg)[#text(size: 8pt)[#claims.len()]],
        table.cell(fill: bg)[#text(size: 8pt)[#if ob != none and ob.at("is_listed", default: false) { "\u{2714}" } else { "--" }]],
      )
    }
  )

  v(0.3em)
  set text(size: 8pt, fill: muted)
  [*OB* = Orange Book listed. Claims column shows number of claims analyzed. Sorted by risk level (highest first).]
}
