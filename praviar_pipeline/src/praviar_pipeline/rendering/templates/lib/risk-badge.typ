// Praviar Pipeline Risk Badge Component
// Colorblind-safe: premium evidence color + icon shape + text label.
// B&W-survivable: every level is identifiable without color via shape and label.
//
// Per research/brand-product-assessment-2026-05-14/09-brand-direction-round2.md §6 + §8.
//
// Usage: #import "risk-badge.typ": risk-badge
//        #risk-badge("high")

#import "colors.typ": risk-color, risk-bg-color, risk-text-color

// ── Icon Characters (distinct shapes per level) ────────────────────────────
// HIGH    = warning triangle      \u{26A0}  — angular, alarm
// MEDIUM  = diamond (rotated)     \u{25C6}  — caution geometry
// LOW     = check mark            \u{2714}  — minor concern but actionable
// CLEAR   = filled circle         \u{25CF}  — settled, complete
//
// The shape carries the meaning. The color is the brand wedge. Both are
// printable in black and white without losing the risk semantic.

#let risk-icon(level) = {
  let l = lower(str(level))
  if l == "high" or l == "blocked" { "\u{26A0}" }           // Warning triangle
  else if l == "medium" or l == "moderate" or l == "caution" { "\u{25C6}" } // Diamond
  else if l == "low" or l == "watch" { "\u{2714}" }          // Check mark
  else if l == "clear" or l == "minimal" { "\u{25CF}" }      // Filled circle
  else { "\u{2022}" }                                        // Bullet fallback
}

// ── Risk Label ─────────────────────────────────────────────────────────────
// Vocabulary reconciled per 01-brand-audit.md recommendation:
// CLEAR (web) and MINIMAL (email) both render as "CLEAR" in the PDF.

#let risk-label(level) = {
  let l = lower(str(level))
  if l == "high" or l == "blocked" { "BLOCKED" }
  else if l == "medium" or l == "moderate" or l == "caution" { "CAUTION" }
  else if l == "low" or l == "watch" { "WATCH" }
  else if l == "clear" or l == "minimal" { "CLEAR" }
  else { upper(str(level)) }
}

// ── Risk Badge ─────────────────────────────────────────────────────────────
// Renders a rounded box: [icon LABEL]

#let risk-badge(level, large: false) = {
  let bg = risk-bg-color(level)
  let fg = risk-text-color(level)
  let border-color = risk-color(level)
  let icon = risk-icon(level)
  let label = risk-label(level)

  let badge-size = if large { 11pt } else { 8pt }
  let h-pad = if large { 10pt } else { 6pt }
  let v-pad = if large { 5pt } else { 3pt }
  let radius = if large { 5pt } else { 3pt }

  box(
    fill: bg,
    stroke: 0.6pt + border-color,
    radius: radius,
    inset: (x: h-pad, y: v-pad),
  )[
    #set text(size: badge-size, weight: "bold", fill: fg)
    #icon #label
  ]
}

// ── Inline Risk Dot ────────────────────────────────────────────────────────
// Compact colored dot for tables (always paired with text label nearby).

#let risk-dot(level) = {
  let c = risk-color(level)
  box(
    width: 8pt,
    height: 8pt,
    radius: 4pt,
    fill: c,
  )
}

// ── Risk Marker (B&W-survivable) ───────────────────────────────────────────
// Combination of color + shape. Use when the PDF may be photocopied.

#let risk-marker(level) = {
  let icon = risk-icon(level)
  let color = risk-color(level)
  set text(size: 10pt, weight: "bold", fill: color)
  icon
}
