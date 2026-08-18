// Praviar Search Methodology

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface, accent, risk-high, risk-low
#import "../lib/typography.typ": font-heading, font-table
#import "../lib/utils.typ": fmt-number

#let render-methodology(data, assets-dir) = {
  let sources-used = data.at("search_sources_used", default: ())
  let source-health = data.at("source_health", default: (:))
  let health-entries = source-health.at("entries", default: ())
  let evidence-scope = data.at("_evidence_scope", default: (:))
  let source-claim = evidence-scope.at("source_claim", default: "Source completion telemetry was not recorded for this artifact.")
  let jurisdiction-claim = evidence-scope.at("jurisdiction_claim", default: "Jurisdiction scope metadata was not recorded for this artifact.")
  let jurisdiction-items = evidence-scope.at("reported_jurisdictions", default: ())
  let coverage-caveat = evidence-scope.at("coverage_caveat", default: "Scope statements describe recorded evidence only and do not certify exhaustive legal clearance.")
  let audit = data.at("audit_trail", default: (:))

  heading(level: 1)[Search Methodology]

  // ── Data Sources ────────────────────────────────────────────────────────
  heading(level: 2)[Data Sources]

  if health-entries.len() > 0 {
    table(
      columns: (1fr, auto, auto),
      align: (left, center, right),
      stroke: 0.5pt + border,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      inset: 6pt,
      // Header
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Source]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Status]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Patents Found]],
      ),
      // Rows
      ..for entry in health-entries {
        let source-name = entry.at("source", default: "Unknown")
        let status = entry.at("status", default: "unknown")
        let count = entry.at("patent_count", default: 0)

        let status-color = if status == "ok" { risk-low }
          else if status == "failed" { risk-high }
          else { muted }

        let status-label = if status == "ok" { "OK" }
          else if status == "failed" { "Failed" }
          else { "Skipped" }

        (
          source-name,
          [#box(width: 8pt, height: 8pt, radius: 4pt, fill: status-color) #text(size: 8.5pt)[#status-label]],
          fmt-number(count),
        )
      }
    )
    v(0.4em)
	  } else if sources-used.len() > 0 {
	    // Fallback: just list source names
	    for src in sources-used [
	      - #src
	    ]
	    v(0.4em)
	  }

  block(
    width: 100%,
    fill: surface,
    stroke: 0.5pt + border,
    radius: 4pt,
    inset: 8pt,
  )[
    #set text(size: 9pt, fill: muted)
    #source-claim
  ]

  v(0.5em)

  // ── Search Funnel ──────────────────────────────────────────────────────
  heading(level: 2)[Patent Screening Funnel]

  {
    let discovered = audit.at("total_patents_discovered", default: 0)
    let after-filter = audit.at("patents_after_hard_filter", default: 0)
    let after-rank = audit.at("patents_after_ranking", default: 0)
    let after-triage = audit.at("patents_after_triage", default: 0)
    let analyzed = audit.at("patents_analyzed", default: 0)

    table(
      columns: (1fr, auto, auto),
      align: (left, right, right),
      stroke: 0.5pt + border,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      inset: 6pt,
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Stage]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Count]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Retained]],
      ),
      [Patents Discovered], fmt-number(discovered), [--],
      [After Hard Filters], fmt-number(after-filter),
        if discovered > 0 { str(calc.round(after-filter / discovered * 100, digits: 1)) + "%" } else { "--" },
      [After Relevance Ranking], fmt-number(after-rank),
        if discovered > 0 { str(calc.round(after-rank / discovered * 100, digits: 1)) + "%" } else { "--" },
      [After AI Triage], fmt-number(after-triage),
        if discovered > 0 { str(calc.round(after-triage / discovered * 100, digits: 1)) + "%" } else { "--" },
      [Deep Analysis], fmt-number(analyzed),
        if discovered > 0 { str(calc.round(analyzed / discovered * 100, digits: 1)) + "%" } else { "--" },
    )

    v(0.4em)
  }

  // ── Funnel Chart (if available) ────────────────────────────────────────
  {
    let has-funnel = data.at("_has_funnel_chart", default: false)
    if has-funnel {
      align(center)[
        #image(
          assets-dir + "/funnel_chart.png",
          width: 4.2in,
          alt: "Patent screening funnel from discovered records to deep analysis",
        )
      ]
      v(0.2em)
      align(center)[
        #set text(size: 8pt, fill: muted)
        _Figure: Patent screening funnel showing progressive filtering._
      ]
      v(0.4em)
    }
  }

	  // ── Jurisdictional Coverage ────────────────────────────────────────────
	  heading(level: 2)[Jurisdictional Coverage]

  [#jurisdiction-claim]

	  v(0.2em)

  if jurisdiction-items.len() > 0 {
	    grid(
	      columns: (auto, 1fr),
	      column-gutter: 1em,
	      row-gutter: 0.3em,
      ..for item in jurisdiction-items {
        let code = item.at("code", default: "")
        let name = item.at("name", default: "")
	        (
	          text(font: font-table, weight: "bold", fill: accent)[#code],
	          [#name],
	        )
	      }
	    )
  }

  v(0.4em)

  block(
    width: 100%,
    fill: surface,
    stroke: 0.5pt + border,
    radius: 4pt,
    inset: 8pt,
  )[
    #set text(size: 8.8pt, fill: muted)
    #coverage-caveat
  ]
	}
