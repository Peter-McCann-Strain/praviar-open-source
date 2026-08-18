// Praviar Pipeline Verification & Quality Section

#import "../lib/colors.typ": ink, muted, border, surface, risk-low, risk-high, risk-moderate
#import "../lib/typography.typ": font-heading, font-mono, font-table
#import "../lib/utils.typ": status-icon, severity-badge

#let render-verification(data) = {
  let verification = data.at("verification", default: (:))
  let checks = verification.at("checks", default: ())
  let failures = data.at("analysis_failures", default: ())
  let limitations = data.at("data_limitations", default: ())
  let review-issues = data.at("review_issues", default: ())
  let llm-models = data.at("llm_models_used", default: (:))

  heading(level: 1)[Verification & Quality]

  // ── Verification Checks ────────────────────────────────────────────────
  if checks.len() > 0 {
    heading(level: 2)[Quality Checks]

    // Summary counts
    {
      let passed = checks.filter(c => c.at("passed", default: false)).len()
      let failed = checks.len() - passed

      grid(
        columns: (1fr, 1fr),
        column-gutter: 12pt,
        block(
          width: 100%,
          fill: risk-low.lighten(85%),
          radius: 4pt,
          inset: 10pt,
          stroke: 0.5pt + risk-low,
        )[
          #align(center)[
            #text(size: 18pt, weight: "bold", fill: risk-low)[#passed]
            #v(0.1em)
            #text(size: 9pt, fill: risk-low.darken(30%))[Checks Passed]
          ]
        ],
        block(
          width: 100%,
          fill: if failed > 0 { risk-high.lighten(85%) } else { surface },
          radius: 4pt,
          inset: 10pt,
          stroke: 0.5pt + if failed > 0 { risk-high } else { border },
        )[
          #align(center)[
            #text(size: 18pt, weight: "bold", fill: if failed > 0 { risk-high } else { muted })[#failed]
            #v(0.1em)
            #text(size: 9pt, fill: if failed > 0 { risk-high.darken(20%) } else { muted })[Checks Failed]
          ]
        ],
      )
      v(0.4em)
    }

    // Checks table
    table(
      columns: (2fr, auto, auto, 3fr),
      align: (left, center, center, left),
      stroke: 0.5pt + border,
      inset: 5pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Check]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Status]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Severity]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Details]],
      ),
      ..for check in checks {
        let name = check.at("check_name", default: "Unknown")
        let passed = check.at("passed", default: false)
        let severity = check.at("severity", default: "info")
        let details = check.at("details", default: "")
        (
          text(size: 8.5pt)[#name],
          status-icon(passed),
          severity-badge(severity),
          text(size: 8pt)[#details],
        )
      }
    )
    v(0.4em)
  }

  // ── Critic Review Issues ───────────────────────────────────────────────
  if review-issues.len() > 0 {
    heading(level: 2)[Critic Review Issues]

    for issue in review-issues {
      let severity = issue.at("severity", default: "major")
      let issue-type = issue.at("issue_type", default: "review_issue")
      let patent-id = issue.at("patent_id", default: "N/A")
      let description = issue.at("description", default: "A report finding requires review.")
      let correction = issue.at("suggested_correction", default: "")
      let issue-color = if severity == "critical" or severity == "major" { risk-high } else { risk-moderate }

      block(
        width: 100%,
        fill: issue-color.lighten(88%),
        stroke: (left: 3pt + issue-color, top: 0.5pt + border, right: 0.5pt + border, bottom: 0.5pt + border),
        radius: (right: 3pt),
        inset: 8pt,
      )[
        #text(size: 8pt, fill: issue-color.darken(25%), weight: "bold")[#upper(severity) · #issue-type]
        #h(0.5em)
        #text(font: font-mono, size: 8pt, weight: "bold")[#patent-id]
        #v(0.15em)
        #text(size: 9pt)[#description]
        #if correction != "" {
          v(0.15em)
          text(size: 8.5pt, fill: muted)[Suggested correction: #correction]
        }
      ]
      v(0.2em)
    }
    v(0.2em)
  }

  // ── Data Limitations ───────────────────────────────────────────────────
  if limitations.len() > 0 {
    heading(level: 2)[Data Limitations]

    for lim in limitations {
      let category = lim.at("category", default: "")
      let desc = lim.at("description", default: "")
      let impact = lim.at("impact", default: "")

      block(
        width: 100%,
        fill: risk-moderate.lighten(85%),
        stroke: (left: 3pt + risk-moderate, top: 0.5pt + border, right: 0.5pt + border, bottom: 0.5pt + border),
        radius: (right: 3pt),
        inset: 8pt,
      )[
        #text(size: 8pt, fill: muted, weight: "bold")[#upper(category)]
        #v(0.1em)
        #text(size: 9pt)[#desc]
        #if impact != "" {
          v(0.1em)
          text(size: 8.5pt, fill: risk-moderate.darken(30%))[Impact: #impact]
        }
      ]
      v(0.2em)
    }
    v(0.2em)
  }

  // ── Analysis Failures ──────────────────────────────────────────────────
  if failures.len() > 0 {
    heading(level: 2)[Analysis Failures]

    table(
      columns: (auto, auto, auto, 2fr, auto),
      align: (left, left, left, left, center),
      stroke: 0.5pt + border,
      inset: 5pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { risk-high.lighten(85%) } else { surface },
      table.header(
        table.cell(fill: risk-high)[#text(fill: surface, weight: "bold", size: 7.5pt)[Patent ID]],
        table.cell(fill: risk-high)[#text(fill: surface, weight: "bold", size: 7.5pt)[Step]],
        table.cell(fill: risk-high)[#text(fill: surface, weight: "bold", size: 7.5pt)[Error Type]],
        table.cell(fill: risk-high)[#text(fill: surface, weight: "bold", size: 7.5pt)[Message]],
        table.cell(fill: risk-high)[#text(fill: surface, weight: "bold", size: 7.5pt)[Recoverable]],
      ),
      ..for failure in failures {
        let pid = failure.at("patent_id", default: "N/A")
        let step = failure.at("step", default: "")
        let etype = failure.at("error_type", default: "")
        let msg = failure.at("error_message", default: "")
        let safe-msg = if msg == "" { "" } else { "Processing failed; protected diagnostics are available to operators." }
        let recoverable = failure.at("recoverable", default: false)
        (
          text(font: font-mono, size: 7.5pt)[#pid],
          text(size: 8pt)[#step],
          text(font: font-mono, size: 7.5pt)[#etype],
          text(size: 8pt)[#safe-msg],
          if recoverable { text(fill: risk-low)[Yes] } else { text(fill: risk-high)[No] },
        )
      }
    )
    v(0.4em)
  }

  // ── Model Attribution ──────────────────────────────────────────────────
  if llm-models.keys().len() > 0 {
    heading(level: 2)[LLM Model Attribution]

    table(
      columns: (1fr, 2fr),
      align: (left, left),
      stroke: 0.5pt + border,
      inset: 6pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Role]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Model]],
      ),
      ..for (role, model) in llm-models.pairs() {
        (
          text(size: 9pt, weight: "bold")[#role],
          text(font: font-mono, size: 8pt)[#model],
        )
      }
    )
  }
}
