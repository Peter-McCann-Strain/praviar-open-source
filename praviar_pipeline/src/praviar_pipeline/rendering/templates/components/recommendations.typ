// Praviar Pipeline Recommendations / Action Items

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface, accent
#import "../lib/typography.typ": font-heading, font-mono

#let render-recommendations(data) = {
  let items = data.at("action_items", default: ())

  heading(level: 1)[Recommendations]

  if items.len() == 0 {
    block(
      width: 100%,
      fill: surface,
      radius: 4pt,
      inset: 12pt,
      stroke: 0.5pt + border,
    )[
      #set text(fill: muted)
      No specific action items were generated for this analysis.
    ]
    return
  }

  // ── Priority Sorting ─────────────────────────────────────────────────
  let priority-order(p) = {
    let l = lower(str(p))
    if l == "critical" { 0 }
    else if l == "high" { 1 }
    else if l == "medium" { 2 }
    else if l == "low" { 3 }
    else { 4 }
  }

  let sorted = items.sorted(key: item => priority-order(item.at("priority", default: "low")))

  // ── Group by Priority ────────────────────────────────────────────────
  let priority-groups = (
    ("critical", "Critical Actions"),
    ("high", "High Priority"),
    ("medium", "Medium Priority"),
    ("low", "Low Priority"),
  )

  for (priority-key, priority-label) in priority-groups {
    let group = sorted.filter(item => lower(str(item.at("priority", default: ""))) == priority-key)
    if group.len() == 0 { continue }

    // Priority header with colored accent
    let header-color = if priority-key == "critical" { rgb("#C2413A") }
      else if priority-key == "high" { rgb("#B87333") }
      else if priority-key == "medium" { accent }
      else { rgb("#5FB7A6") }

    heading(level: 2)[#priority-label]

    for (idx, item) in group.enumerate() {
      let action-type = item.at("action_type", default: "")
      let description = item.at("description", default: "")
      let patent-ids = item.at("patent_ids", default: ())
      let reasoning = item.at("reasoning", default: "")
      let timeline = item.at("estimated_timeline", default: "")

      // PDF/UA compilation uses only the bundled Libertinus fonts. Keep this
      // marker textual so an action can never fail export because an emoji
      // glyph is unavailable.
      let marker = if action-type == "license" { "LIC" }
        else if action-type == "design_around" { "D/A" }
        else if action-type == "challenge_ipr" { "IPR" }
        else if action-type == "monitor" { "MON" }
        else if action-type == "accept_risk" { "ACK" }
        else if action-type == "halt" { "STOP" }
        else { "ACT" }

      block(
        width: 100%,
        fill: header-color.lighten(92%),
        stroke: (left: 3pt + header-color, top: 0.5pt + border, right: 0.5pt + border, bottom: 0.5pt + border),
        radius: (right: 4pt),
        inset: 10pt,
      )[
        // Type badge
        #grid(
          columns: (auto, 1fr),
          column-gutter: 8pt,
          // Font-safe action marker + type
          align(center + horizon)[
            #box(
              fill: header-color,
              radius: 3pt,
              inset: (x: 5pt, y: 3pt),
            )[
              #text(size: 7pt, fill: surface, weight: "bold")[#marker]
            ]
          ],
          [
            // Action type label
            #text(size: 8pt, fill: muted, weight: "bold")[#upper(str(action-type).replace("_", " "))]
            #v(0.15em)
            // Description
            #text(size: 10pt, weight: "bold")[#description]

            // Reasoning
            #if reasoning != "" {
              v(0.2em)
              text(size: 9pt)[#reasoning]
            }

            // Related patents
            #if patent-ids.len() > 0 {
              v(0.2em)
              text(size: 8.5pt, fill: muted)[
                Related patents: #text(font: font-mono, size: 8pt)[#patent-ids.join(", ")]
              ]
            }

            // Timeline
            #if timeline != "" {
              v(0.15em)
              text(size: 8.5pt, fill: accent)[Timeline: #timeline]
            }
          ],
        )
      ]
      v(0.3em)
    }
  }
}
