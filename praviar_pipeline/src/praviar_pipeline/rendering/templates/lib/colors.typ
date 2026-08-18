// Praviar Design System - Forensic Teal + Clinical Copper
//
// Every risk indicator uses color + icon shape + text label so the
// document remains legible printed in B&W. The premium palette balances
// clinical trust, evidence review, and decisive counsel-facing judgment.

// ── Brand Palette ──────────────────────────────────────────────────────────

#let ink = rgb("#0B1F24")
#let forensic-teal = rgb("#0E6F68")
#let clinical-mint = rgb("#5FB7A6")
#let clinical-copper = rgb("#B87333")
#let paper = rgb("#F6F4EF")
#let deep-teal = rgb("#0B4F4C")
#let soft-mint = rgb("#D7ECE5")
#let risk-red = rgb("#C2413A")
#let risk-red-deep = rgb("#7F1D1D")

#let accent = forensic-teal
#let surface = paper
#let border = rgb("#C8D8D2")
#let body-fg = ink
#let muted = rgb("#516F68")

// ── Risk Colors — premium evidence semantics ───────────────────────────────

#let risk-high = risk-red
#let risk-moderate = clinical-copper
#let risk-low = forensic-teal
#let risk-clear = clinical-mint

// ── Risk Backgrounds (tinted, B&W survivable via pattern in risk-badge.typ) ─

#let risk-high-bg = rgb("#FDECEC")
#let risk-moderate-bg = rgb("#F7EEE5")
#let risk-low-bg = rgb("#D7ECE5")
#let risk-clear-bg = rgb("#EAF6F2")

// ── Risk Text (WCAG AA 4.5:1 on paper and tinted backgrounds) ───────────────

#let risk-high-text = risk-red-deep
#let risk-moderate-text = rgb("#8A4F1F")
#let risk-low-text = rgb("#0B4F4C")
#let risk-clear-text = forensic-teal

// ── Claim Element Status Colors ────────────────────────────────────────────

#let element-met = risk-red
#let element-partial = clinical-copper
#let element-not-met = forensic-teal
#let element-unclear = muted

// ── Table Stripe — vellum/paper feel ───────────────────────────────────────

#let stripe-even = paper
#let stripe-odd = paper

// ── Lookup Functions ───────────────────────────────────────────────────────

#let risk-color(level) = {
  let l = lower(str(level))
  if l == "high" or l == "blocked" { risk-high }
  else if l == "medium" or l == "moderate" or l == "caution" { risk-moderate }
  else if l == "low" or l == "watch" { risk-low }
  else if l == "clear" or l == "minimal" { risk-clear }
  else { muted }
}

#let risk-bg-color(level) = {
  let l = lower(str(level))
  if l == "high" or l == "blocked" { risk-high-bg }
  else if l == "medium" or l == "moderate" or l == "caution" { risk-moderate-bg }
  else if l == "low" or l == "watch" { risk-low-bg }
  else if l == "clear" or l == "minimal" { risk-clear-bg }
  else { surface }
}

#let risk-text-color(level) = {
  let l = lower(str(level))
  if l == "high" or l == "blocked" { risk-high-text }
  else if l == "medium" or l == "moderate" or l == "caution" { risk-moderate-text }
  else if l == "low" or l == "watch" { risk-low-text }
  else if l == "clear" or l == "minimal" { risk-clear-text }
  else { body-fg }
}

#let element-status-color(status) = {
  let s = lower(str(status))
  if s == "met" { element-met }
  else if s == "partially_met" or s == "partial" { element-partial }
  else if s == "not_met" { element-not-met }
  else { element-unclear }
}
