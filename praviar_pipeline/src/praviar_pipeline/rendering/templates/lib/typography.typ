// Praviar Typography System
// Per research/brand-product-assessment-2026-05-14/09-brand-direction-round2.md §3 + §8
//
// Active export fonts must resolve in local/CI Typst builds. Licensed launch
// faces can be introduced later, but unresolved names here create noisy PDF
// compiles and invisible typography degradation.

#import "colors.typ": forensic-teal, ink, deep-teal, body-fg, muted, border, clinical-copper

// ── Font Stacks ────────────────────────────────────────────────────────────

#let font-display = (
  "New Computer Modern",
  "Libertinus Serif",
)

#let font-body = (
  "Libertinus Serif",
  "New Computer Modern",
)

#let font-heading = (
  "New Computer Modern",
  "Libertinus Serif",
)

#let font-table = (
  // Body font for tables (smaller size).
  "Libertinus Serif",
  "New Computer Modern",
)

#let font-mono = (
  "DejaVu Sans Mono",
)

// Italic display treatment is reserved for quoted patent text per the brand spec §6.3.
#let font-quoted-claim = (
  "Libertinus Serif",
  "New Computer Modern",
)

// ── Base Sizes ─────────────────────────────────────────────────────────────

#let size-body = 10pt
#let size-small = 8.5pt
#let size-caption = 8pt
#let size-code = 8.5pt
#let size-h1 = 18pt // Bumped — display-class heading
#let size-h2 = 13pt
#let size-h3 = 11pt
#let size-h4 = 10pt
#let size-cover-title = 32pt // Display face on cover page

// ── Apply Typography ───────────────────────────────────────────────────────
// Call as `#show: apply-typography` in the main document.

#let apply-typography(doc) = {
  // Base text
  set text(
    font: font-body,
    size: size-body,
    fill: body-fg,
    lang: "en",
    hyphenate: true,
  )

  // Paragraph spacing
  set par(
    leading: 0.65em,
    justify: true,
  )

  // Heading numbering
  set heading(numbering: "1.1")

  // Heading level 1 - section headers (display italic, premium ink)
  show heading.where(level: 1): it => {
    v(1.2em)
    block(width: 100%)[
      #set text(font: font-display, size: size-h1, weight: "regular", fill: ink, style: "italic")
      #it
      #v(0.3em)
      #line(length: 100%, stroke: 0.5pt + border)
    ]
    v(0.6em)
  }

  // Heading level 2 - subsection headers (sans, evidence slate)
  show heading.where(level: 2): it => {
    v(0.8em)
    block[
      #set text(font: font-heading, size: size-h2, weight: "semibold", fill: deep-teal)
      #it
    ]
    v(0.4em)
  }

  // Heading level 3
  show heading.where(level: 3): it => {
    v(0.6em)
    block[
      #set text(font: font-heading, size: size-h3, weight: "semibold", fill: deep-teal)
      #it
    ]
    v(0.3em)
  }

  // Heading level 4
  show heading.where(level: 4): it => {
    v(0.4em)
    block[
      #set text(font: font-heading, size: size-h4, weight: "semibold", fill: body-fg)
      #it
    ]
    v(0.2em)
  }

  // Raw / code blocks.
  show raw: set text(font: font-mono, size: size-code)

  // Tables — use heading font, smaller size
  show table: set text(font: font-table, size: size-small)

  doc
}

// ── Cover-page title ───────────────────────────────────────────────────────
// Display-class typography for the PDF cover page only.

#let cover-title(text-content) = {
  set text(
    font: font-display,
    size: size-cover-title,
    weight: "regular",
    fill: ink,
    style: "italic",
  )
  text-content
}

// ── Quoted patent claim ────────────────────────────────────────────────────
// Italic quoted text in body-fg color, indented with a left rule.

#let quoted-claim(content) = {
  block(
    inset: (left: 1em, top: 0.4em, bottom: 0.4em, right: 0.5em),
    stroke: (left: 2pt + forensic-teal),
    fill: rgb("#F6F4EF"),
  )[
    #set text(font: font-quoted-claim, style: "italic", fill: body-fg)
    #content
  ]
}

// ── Folio (page number) - copper accent ───────────────────────────────────

#let folio-number(num) = {
  set text(font: font-display, size: 9pt, style: "italic", fill: clinical-copper)
  str(num)
}
