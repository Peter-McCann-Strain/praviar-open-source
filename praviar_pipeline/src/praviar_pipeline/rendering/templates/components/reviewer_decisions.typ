// Praviar Pipeline Reviewer Decisions — Final Appendix
// Ticket: SG-reviewer (WS-3 finishing work)
//
// Renders each attorney accept / reject / edit decision captured against
// individual findings of this analysis. Decisions are stored in the API DB
// (AnalysisReviewerDecision) and passed into the Typst payload under
// `reviewer_decisions` as a list of dicts:
//   - finding_type   (str)   e.g. "patent" / "claim" / "recommendation"
//   - finding_ref    (str)   stable reference, e.g. "US1234567B2"
//   - decision       (str)   "accept" | "reject" | "edit"
//   - note           (str)   optional reviewer note
//   - edited_text    (str)   optional replacement text when decision=edit
//   - reviewer_name  (str)   display name snapshot at decision time
//   - reviewer_email (str)   email snapshot at decision time
//   - created_at     (str)   ISO-8601 timestamp (UTC)
//
// If no decisions are recorded the appendix prints a single line so the
// reader still gets an explicit statement of the review status.

#import "../lib/colors.typ": ink, border, surface, muted, risk-low, risk-high, risk-moderate, risk-low-bg, risk-high-bg, risk-moderate-bg, risk-low-text, risk-high-text, risk-moderate-text

#let _decision_color(decision) = {
  let d = lower(str(decision))
  if d == "accept" { risk-low }
  else if d == "reject" { risk-high }
  else if d == "edit" { risk-moderate }
  else { muted }
}

#let _decision_bg(decision) = {
  let d = lower(str(decision))
  if d == "accept" { risk-low-bg }
  else if d == "reject" { risk-high-bg }
  else if d == "edit" { risk-moderate-bg }
  else { surface }
}

#let _decision_text_color(decision) = {
  let d = lower(str(decision))
  if d == "accept" { risk-low-text }
  else if d == "reject" { risk-high-text }
  else if d == "edit" { risk-moderate-text }
  else { ink }
}

#let _fmt_date(ts) = {
  // Extract yyyy-mm-dd prefix from an ISO-8601 timestamp; fall back to raw.
  let s = str(ts)
  if s.len() >= 10 { s.slice(0, 10) } else { s }
}

#let _truncate(note, limit) = {
  let s = str(note)
  if s.len() <= limit { s } else { s.slice(0, limit) + " (…)" }
}

#let reviewer-decisions-section(data) = {
  let decisions = data.at("reviewer_decisions", default: ())

  if decisions.len() > 0 {
    pagebreak()
  } else {
    v(1em)
  }
  heading(level: 1)[Reviewer Decisions]

  text(size: 9pt)[
    Per-finding accept / reject / edit decisions captured during attorney
    review of this analysis. Each decision is printed with the reviewer's
    name as recorded at decision time.
  ]

  v(0.5em)

  if decisions.len() == 0 {
    text(size: 10pt, fill: muted)[
      No reviewer decisions recorded for this analysis.
    ]
    return
  }

  set text(size: 8.5pt)
  table(
    columns: (1.4fr, auto, 1.3fr, auto, 2fr),
    align: (left, center, left, left, left),
    stroke: 0.5pt + border,
    inset: 5pt,
    fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
    table.header(
      table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Finding]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Decision]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Reviewer]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Date]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Note / Edit]],
    ),
    ..for d in decisions {
      let ftype = d.at("finding_type", default: "")
      let fref = d.at("finding_ref", default: "")
      let decision = d.at("decision", default: "")
      let note = d.at("note", default: "")
      let edited = d.at("edited_text", default: "")
      let rname = d.at("reviewer_name", default: "")
      let created = d.at("created_at", default: "")

      let finding-cell = [#text(weight: "bold")[#ftype] \ #text(size: 8pt, fill: muted)[#fref]]

      let decision-cell = box(
        fill: _decision_bg(decision),
        stroke: 0.5pt + _decision_color(decision),
        radius: 2pt,
        inset: (x: 5pt, y: 2pt),
      )[#text(fill: _decision_text_color(decision), weight: "bold")[#upper(str(decision))]]

      let detail = if decision == "edit" and str(edited).len() > 0 {
        [
          #if str(note).len() > 0 [#text(style: "italic")[#_truncate(note, 200)] \ ]
          #text(size: 8pt)[#strong[Edit:] #_truncate(edited, 200)]
        ]
      } else if str(note).len() > 0 {
        [#text(style: "italic")[#_truncate(note, 200)]]
      } else {
        [#text(fill: muted)[—]]
      }

      (
        finding-cell,
        decision-cell,
        [#rname],
        [#_fmt_date(created)],
        detail,
      )
    }
  )
}
