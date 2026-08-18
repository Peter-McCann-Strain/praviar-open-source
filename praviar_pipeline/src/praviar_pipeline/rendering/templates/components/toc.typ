// Praviar Pipeline Table of Contents

#import "../lib/colors.typ": ink, border
#import "../lib/typography.typ": font-heading

#let render-toc() = {
  // Title (not numbered -- uses heading level 1 without numbering)
  align(center)[
    #v(0.3in)
    #text(font: font-heading, size: 18pt, weight: "bold", fill: ink)[
      Table of Contents
    ]
    #v(0.2in)
    #line(length: 2in, stroke: 0.5pt + border)
    #v(0.4in)
  ]

  // Typst built-in outline
  outline(
    title: none,
    indent: 1.5em,
    depth: 3,
  )

  pagebreak()
}
