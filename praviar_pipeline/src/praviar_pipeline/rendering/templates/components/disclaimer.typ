// Praviar Pipeline Disclaimer / Back Page

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface
#import "../lib/typography.typ": font-heading, font-body
#import "../lib/utils.typ": fmt-date

#let render-disclaimer(data, branding) = {
  let disclaimer-text = data.at("disclaimer", default: "")
  let version = data.at("praviar_pipeline_version", default: "")
  let generated = data.at("generated_at", default: none)
  let report-id = data.at("report_id", default: "")
  let hide-branding = branding.at("hide_praviar_pipeline_branding", default: false)
  let suppress-praviar-branding = branding.at("suppresses_praviar_branding", default: hide-branding)
  let custom-disclaimer = branding.at("disclaimer_text", default: none)

  // Python guarantees this contains the mandatory disclaimer before any custom notice.
  let final-disclaimer = if custom-disclaimer != none { custom-disclaimer } else { disclaimer-text }

  pagebreak()

  v(1fr)

  // ── Disclaimer Box ─────────────────────────────────────────────────────
  block(
    width: 100%,
    fill: surface,
    stroke: 1pt + border,
    radius: 6pt,
    inset: 20pt,
  )[
    #align(center)[
      #text(font: font-heading, size: 14pt, weight: "bold", fill: ink)[
        Important Disclaimer
      ]
    ]
    #v(0.5em)
    #line(length: 100%, stroke: 0.5pt + border)
    #v(0.5em)

    #set text(size: 9.5pt)
    #set par(justify: true, leading: 0.7em)
    #final-disclaimer
  ]

  v(0.8em)

  // ── Confidentiality Notice ─────────────────────────────────────────────
  block(
    width: 100%,
    fill: ink.lighten(95%),
    stroke: 0.5pt + ink.lighten(70%),
    radius: 4pt,
    inset: 14pt,
  )[
    #set text(size: 8.5pt, fill: ink)
    #text(weight: "bold")[CONFIDENTIALITY NOTICE]
    #v(0.3em)
    This document contains confidential and proprietary information. It is intended
    solely for the use of the individual or entity to whom it is addressed. If you
    are not the intended recipient, you are hereby notified that any disclosure,
    copying, distribution, or use of the contents of this document is strictly
    prohibited. If you have received this document in error, please notify the
    sender immediately and destroy all copies.
  ]

  v(0.8em)

  // ── Document Metadata ──────────────────────────────────────────────────
  align(center)[
    #set text(size: 8pt, fill: muted)
    #grid(
      columns: (auto, auto),
      column-gutter: 1em,
      row-gutter: 0.3em,
      align: (right, left),
      [Report ID:], [#report-id],
      [Generated:], [#fmt-date(generated)],
      ..if not suppress-praviar-branding {
        ([Praviar Version:], [v#version])
      } else { () },
    )
  ]

  v(0.5em)

  // ── Footer Logo / Branding ─────────────────────────────────────────────
  if not suppress-praviar-branding {
    align(center)[
      #line(length: 2in, stroke: 0.5pt + border)
      #v(0.3em)
      #text(font: font-heading, size: 10pt, fill: deep-teal, tracking: 0.1em)[
        PRAVIAR
      ]
      #v(0.1em)
      #text(size: 7pt, fill: muted)[
        AI-Powered Patent Intelligence
      ]
    ]
  }

  v(1fr)
}
