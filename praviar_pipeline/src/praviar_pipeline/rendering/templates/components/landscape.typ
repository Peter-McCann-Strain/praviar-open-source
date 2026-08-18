// Praviar Patent Landscape Overview
// Embeds pre-rendered charts: risk distribution, patent timeline, assignee distribution.

#import "../lib/colors.typ": ink, muted, border, surface, risk-high, risk-moderate, risk-low, risk-clear
#import "../lib/typography.typ": font-heading

#let render-landscape(data, assets-dir) = {
  let analyses = data.at("patent_analyses", default: ())

  heading(level: 1)[Patent Landscape]

  // ── Summary Statistics ─────────────────────────────────────────────────
  {
    let total = analyses.len()
    let high-count = analyses.filter(a => {
      let rl = lower(str(a.at("risk_level", default: "")))
      rl == "high"
    }).len()
    let med-count = analyses.filter(a => {
      let rl = lower(str(a.at("risk_level", default: "")))
      rl == "medium" or rl == "moderate"
    }).len()
    let low-count = analyses.filter(a => {
      let rl = lower(str(a.at("risk_level", default: "")))
      rl == "low"
    }).len()
    let clear-count = analyses.filter(a => {
      let rl = lower(str(a.at("risk_level", default: "")))
      rl == "clear"
    }).len()

    // Stats cards row
    grid(
      columns: (1fr, 1fr, 1fr, 1fr),
      column-gutter: 8pt,
      ..for (label, count, color) in (
        ("High Risk", high-count, risk-high),
        ("Moderate", med-count, risk-moderate),
        ("Low Risk", low-count, risk-low),
        ("Clear", clear-count, risk-clear),
      ) {
        (
          block(
            width: 100%,
            fill: surface,
            stroke: (top: 3pt + color, left: 0.5pt + border, right: 0.5pt + border, bottom: 0.5pt + border),
            radius: (bottom: 4pt),
            inset: 10pt,
          )[
            #align(center)[
              #text(font: font-heading, size: 20pt, weight: "bold", fill: color)[#count]
              #v(0.15em)
              #text(size: 8.5pt, fill: muted)[#label]
            ]
          ],
        )
      }
    )
    v(0.6em)
  }

  // ── Risk Distribution Chart ────────────────────────────────────────────
  {
    let has-risk-dist = data.at("_has_risk_distribution", default: false)
    if has-risk-dist {
      heading(level: 2)[Risk Distribution]
      align(center)[
        #image(
          assets-dir + "/risk_distribution.png",
          width: 4.5in,
          alt: "Distribution of risk levels across analyzed patents",
        )
      ]
      align(center)[
        #set text(size: 8pt, fill: muted)
        _Figure: Distribution of risk levels across analyzed patents._
      ]
      v(0.4em)
    }
  }

  // ── Patent Timeline Chart ──────────────────────────────────────────────
  {
    let has-timeline = data.at("_has_patent_timeline", default: false)
    if has-timeline {
      heading(level: 2)[Patent Expiry Timeline]
      align(center)[
        #image(
          assets-dir + "/patent_timeline.png",
          width: 5in,
          alt: "Timeline of reported patent expiry dates by risk level",
        )
      ]
      align(center)[
        #set text(size: 8pt, fill: muted)
        _Figure: Timeline of patent expiry dates, colored by risk level._
      ]
      v(0.4em)
    }
  }

  // ── Assignee Distribution Chart ────────────────────────────────────────
  {
    let has-assignee = data.at("_has_assignee_chart", default: false)
    if has-assignee {
      heading(level: 2)[Assignee Distribution]
      align(center)[
        #image(
          assets-dir + "/assignee_chart.png",
          width: 4.5in,
          alt: "Distribution of analyzed patents by assignee",
        )
      ]
      align(center)[
        #set text(size: 8pt, fill: muted)
        _Figure: Patent portfolio distribution by assignee._
      ]
      v(0.4em)
    }
  }

  // ── Top Assignees Table (from data) ────────────────────────────────────
  if analyses.len() > 0 {
    // Collect assignees and count patents per assignee
    let assignee-map = (:)
    for a in analyses {
      let assignee = a.at("assignee", default: "Unknown")
      if assignee != "" and assignee != none {
        let current = assignee-map.at(assignee, default: 0)
        assignee-map.insert(assignee, current + 1)
      }
    }

    if assignee-map.len() > 0 {
      heading(level: 2)[Top Patent Holders]

      // Sort by count descending — collect into pairs
      let pairs = assignee-map.pairs()
      let sorted-pairs = pairs.sorted(key: p => -p.at(1))
      let top = sorted-pairs.slice(0, calc.min(10, sorted-pairs.len()))

      table(
        columns: (1fr, auto),
        align: (left, right),
        stroke: 0.5pt + border,
        fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
        inset: 6pt,
        table.header(
          table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Assignee]],
          table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Patents]],
        ),
        ..for (assignee, count) in top {
          (assignee, str(count))
        }
      )
    }
  }
}
