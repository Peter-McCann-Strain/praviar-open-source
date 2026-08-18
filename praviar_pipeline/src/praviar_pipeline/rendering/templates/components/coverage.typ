// Praviar Pipeline Search Coverage Banner
// Compact factual summary of source-health for the report front matter.
// Renders directly after the cover / before the executive summary so attorneys
// see coverage limitations at a glance.

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface, accent, risk-high, risk-moderate, risk-low, risk-high-bg, risk-moderate-bg, risk-low-bg, risk-high-text, risk-moderate-text, risk-low-text
#import "../lib/typography.typ": font-heading, font-body, font-mono
#import "../lib/utils.typ": fmt-number

#let render-coverage(data) = {
  let source-health = data.at("source_health", default: (:))
  let entries = source-health.at("entries", default: ())

  let has-no-entries = entries.len() == 0
  let ok-entries = entries.filter(e => e.at("status", default: "") == "ok")
  let failed-entries = entries.filter(e => {
    let status = e.at("status", default: "")
    status == "failed" or status == "not_configured"
  })
  let skipped-entries = entries.filter(e => e.at("status", default: "") == "skipped")

  let total = entries.len()
  let ok-count = ok-entries.len()
  let failed-count = failed-entries.len()
  let skipped-count = skipped-entries.len()

  // Determine banner tone: red if any failed, amber if any skipped, green otherwise.
  let has-failed = failed-count > 0
  let has-skipped = skipped-count > 0
  let bg-color = if has-no-entries { risk-moderate-bg }
    else if has-failed { risk-high-bg }
    else if has-skipped { risk-moderate-bg }
    else { risk-low-bg }
  let stroke-color = if has-no-entries { risk-moderate }
    else if has-failed { risk-high }
    else if has-skipped { risk-moderate }
    else { risk-low }
  let text-color = if has-no-entries { risk-moderate-text }
    else if has-failed { risk-high-text }
    else if has-skipped { risk-moderate-text }
    else { risk-low-text }

  let confidence-impact = if has-no-entries {
    "Unknown (source-health telemetry was not recorded in this artifact)."
  } else if has-failed {
    if failed-count >= 3 {
      "High (findings below reflect a substantially reduced dataset)."
    } else {
      "Moderate (findings below reflect a reduced dataset)."
    }
  } else if has-skipped {
    "Low (some sources skipped by configuration)."
  } else {
    "None recorded (all configured source requests completed)."
  }

  heading(level: 1)[Search Coverage]

  block(
    width: 100%,
    fill: bg-color,
    stroke: 0.75pt + stroke-color,
    radius: 4pt,
    inset: 12pt,
  )[
    #set text(font: font-body, size: 10pt, fill: text-color)

    #if has-no-entries [
      #strong[Source-health telemetry not recorded.] \
      Verify configured source requests before relying on absence-of-risk conclusions.
    ] else [
      #strong[Configured source requests: #fmt-number(ok-count) of #fmt-number(total) completed] \
      (#fmt-number(failed-count) unavailable/not configured, #fmt-number(skipped-count) skipped).
    ]

    #if not has-no-entries and failed-entries.len() > 0 {
      v(0.4em)
      set text(size: 9.5pt)
      strong[Unavailable or not configured: ]
      let failed-strs = failed-entries.map(e => {
        let name = e.at("source", default: "unknown")
        let msg = e.at("error_message", default: "")
        let safe = "Provider request failed; protected diagnostics are available to operators."
        if msg == "" { name } else { name + " (" + safe + ")" }
      })
      failed-strs.join("; ")
    }

    #if not has-no-entries and skipped-entries.len() > 0 {
      v(0.4em)
      set text(size: 9.5pt)
      strong[Skipped: ]
      skipped-entries.map(e => e.at("source", default: "unknown")).join(", ")
    }

    #v(0.4em)
    #set text(size: 9.5pt)
    #strong[Confidence impact:] #confidence-impact
  ]

  v(0.4em)
}
