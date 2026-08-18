// Praviar Utility Functions
// Date formatting, text truncation, number formatting, duration display.

#import "colors.typ": risk-clear, risk-high, risk-high-bg, risk-high-text, risk-moderate-bg, risk-moderate-text, surface, muted

// ── Date Formatting ────────────────────────────────────────────────────────
// Parses ISO 8601 date strings (2026-03-25T14:30:00Z) into readable format.

// Shared date parsing: extracts (year, month-num, day) from an ISO string.
#let _parse_date_parts(s) = {
  let parts = str(s).split("T").at(0).split("-")
  if parts.len() < 3 { return none }
  let year = parts.at(0)
  let month-num = int(parts.at(1))
  let day = parts.at(2)
  (year: year, month-num: month-num, day: day)
}

#let fmt-date(date-str) = {
  if date-str == none { return "N/A" }
  let parsed = _parse_date_parts(date-str)
  if parsed == none { return str(date-str) }
  let months = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
  )
  let month-idx = parsed.month-num - 1
  if month-idx >= 0 and month-idx < 12 {
    return months.at(month-idx) + " " + str(int(parsed.day)) + ", " + parsed.year
  }
  return parsed.year + "-" + str(parsed.month-num) + "-" + parsed.day
}

// Short date: Mar 25, 2026
#let fmt-date-short(date-str) = {
  if date-str == none { return "N/A" }
  let parsed = _parse_date_parts(date-str)
  if parsed == none { return str(date-str) }
  let months = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
  )
  let month-idx = parsed.month-num - 1
  if month-idx >= 0 and month-idx < 12 {
    return months.at(month-idx) + " " + str(int(parsed.day)) + ", " + parsed.year
  }
  return parsed.year + "-" + str(parsed.month-num) + "-" + parsed.day
}

// ── Text Truncation ────────────────────────────────────────────────────────

#let truncate(text, max-chars) = {
  let s = str(text)
  if s.len() <= max-chars { s }
  else { s.slice(0, max-chars - 1) + "\u{2026}" }
}

// ── Duration Formatting ────────────────────────────────────────────────────
// Converts seconds (float) to human-readable: "2m 34s" or "1.2s"

#let fmt-duration(seconds) = {
  if seconds == none { return "N/A" }
  let secs = float(seconds)
  if secs < 0.1 { return "<0.1s" }
  if secs < 60 {
    return str(calc.round(secs, digits: 1)) + "s"
  }
  let mins = calc.floor(secs / 60)
  let remainder = calc.round(calc.rem(secs, 60), digits: 0)
  return str(int(mins)) + "m " + str(int(remainder)) + "s"
}

// ── Number Formatting ──────────────────────────────────────────────────────
// Adds comma separators: 1234567 -> "1,234,567"

#let fmt-number(n) = {
  if n == none { return "0" }
  let neg = n < 0
  let abs-n = if neg { -n } else { n }
  let s = str(int(abs-n))
  let result = ""
  let count = 0
  // Build from right to left
  let chars = s.clusters()
  let total = chars.len()
  for i in range(total) {
    let idx = total - 1 - i
    if count > 0 and calc.rem(count, 3) == 0 {
      result = "," + result
    }
    result = chars.at(idx) + result
    count = count + 1
  }
  if neg { "-" + result } else { result }
}

// ── Currency Formatting ────────────────────────────────────────────────────

#let fmt-usd(amount) = {
  if amount == none { return "$0.00" }
  let a = calc.round(float(amount), digits: 2)
  let s = str(a)
  // Ensure two decimal places
  if "." not in s { s = s + ".00" }
  else {
    let parts = s.split(".")
    let dec = parts.at(1)
    if dec.len() == 1 { s = s + "0" }
  }
  "$" + s
}

// ── Percentage Formatting ──────────────────────────────────────────────────

#let fmt-pct(value, digits: 1) = {
  if value == none { return "N/A" }
  str(calc.round(float(value) * 100, digits: digits)) + "%"
}

// ── Safe Dictionary Access ─────────────────────────────────────────────────
// Shorthand for .at(key, default: fallback)

#let get(dict, key, fallback: none) = {
  dict.at(key, default: fallback)
}

// ── Risk Level Sort Order ─────────────────────────────────────────────────
// Returns numeric order for sorting: HIGH=0, MEDIUM=1, LOW=2, CLEAR=3, else=4.

#let risk-order(level) = {
  let l = lower(str(level))
  if l == "high" { 0 }
  else if l == "medium" or l == "moderate" { 1 }
  else if l == "low" { 2 }
  else if l == "clear" { 3 }
  else { 4 }
}

// ── Status Icon ────────────────────────────────────────────────────────────

#let status-icon(passed) = {
  if passed { text(fill: risk-clear)[\u{2714}] }
  else { text(fill: risk-high)[\u{2718}] }
}

// ── Severity Badge ─────────────────────────────────────────────────────────

#let severity-badge(severity) = {
  let s = lower(str(severity))
  let (bg, fg) = if s == "critical" or s == "error" {
    (risk-high-bg, risk-high-text)
  } else if s == "warning" {
    (risk-moderate-bg, risk-moderate-text)
  } else if s == "info" {
    (rgb("#EAF6F2"), rgb("#0B4F4C"))
  } else {
    (surface, muted)
  }
  box(
    fill: bg,
    radius: 2pt,
    inset: (x: 4pt, y: 2pt),
  )[#set text(size: 7pt, weight: "bold", fill: fg); #upper(s)]
}
