// Praviar Pipeline Appendices
// A) Full patent listing  B) Search parameters  C) LLM models
// D) Methodology notes    E) Cost summary

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface, accent
#import "../lib/typography.typ": font-heading, font-mono, font-table
#import "../lib/risk-badge.typ": risk-badge
#import "../lib/utils.typ": fmt-date-short, truncate, fmt-number, fmt-usd, fmt-duration, risk-order

#let render-appendices(data, branding) = {
  let analyses = data.at("patent_analyses", default: ())
  let sources-used = data.at("search_sources_used", default: ())
  let llm-models = data.at("llm_models_used", default: (:))
  let audit = data.at("audit_trail", default: (:))
  let timing = audit.at("timing_data", default: ())
  let total-input = data.at("total_input_tokens", default: 0)
  let total-output = data.at("total_output_tokens", default: 0)
  let cost = data.at("estimated_cost_usd", default: 0.0)
  let step-usage = data.at("step_token_usage", default: ())
  let evidence-scope = data.at("_evidence_scope", default: (:))
  let patent-search-step = evidence-scope.at("patent_search_step", default: "Patent source completion was not recorded in this artifact; review the run configuration before relying on negative findings.")
  let hide-branding = branding.at("hide_praviar_pipeline_branding", default: false)
  let suppress-praviar-branding = branding.at("suppresses_praviar_branding", default: hide-branding)

  heading(level: 1)[Appendices]

  // ══════════════════════════════════════════════════════════════════════
  // Appendix A: Full Patent Listing
  // ══════════════════════════════════════════════════════════════════════
  heading(level: 2)[Appendix A: Complete Patent Listing]

  if analyses.len() > 0 {
    // Sort by risk: HIGH first
    let sorted = analyses.sorted(key: a => risk-order(a.at("risk_level", default: "clear")))

    set text(size: 7.5pt)

    table(
      columns: (auto, 2.5fr, 1fr, auto, auto),
      align: (left, left, left, center, center),
      stroke: 0.5pt + border,
      inset: 4pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Patent ID]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Title]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Assignee]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Risk]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Expiry]],
      ),
      ..for patent in sorted {
        let pid = patent.at("patent_id", default: "N/A")
        let title = patent.at("title", default: "")
        let assignee = patent.at("assignee", default: "")
        let risk-level = patent.at("risk_level", default: "clear")
        let expiry = patent.at("expiry_date", default: none)
        (
          text(font: font-mono)[#pid],
          truncate(title, 60),
          truncate(assignee, 30),
          risk-badge(risk-level),
          if expiry != none { fmt-date-short(expiry) } else { "N/A" },
        )
      }
    )
  } else {
    text(fill: muted)[No patents were analyzed.]
  }

  v(0.6em)

  // ══════════════════════════════════════════════════════════════════════
  // Appendix B: Search Parameters
  // ══════════════════════════════════════════════════════════════════════
  heading(level: 2)[Appendix B: Search Parameters]

  {
    let compound = data.at("compound", default: (:))
    let name = compound.at("name", default: "N/A")
    let smiles = compound.at("canonical_smiles", default: none)
    let inchi-key = compound.at("inchi_key", default: none)

    table(
      columns: (auto, 1fr),
      align: (right, left),
      stroke: 0.5pt + border,
      inset: 6pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      [*Target Compound*], name,
      [*SMILES Query*], if smiles != none { text(font: font-mono, size: 7.5pt)[#smiles] } else { "N/A" },
      [*InChIKey*], if inchi-key != none { text(font: font-mono, size: 7.5pt)[#inchi-key] } else { "N/A" },
      [*Search Sources*], if sources-used.len() > 0 { sources-used.join(", ") } else { "N/A" },
      [*Execution Profile*], data.at("execution_profile", default: "world_class_adaptive"),
    )
  }

  v(0.6em)

  // ══════════════════════════════════════════════════════════════════════
  // Appendix C: LLM Model Versions
  // ══════════════════════════════════════════════════════════════════════
  heading(level: 2)[Appendix C: LLM Model Versions]

  if llm-models.keys().len() > 0 {
    table(
      columns: (1fr, 2fr),
      align: (left, left),
      stroke: 0.5pt + border,
      inset: 6pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Pipeline Role]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Model Identifier]],
      ),
      ..for (role, model) in llm-models.pairs() {
        (
          text(weight: "bold")[#role],
          text(font: font-mono, size: 8.5pt)[#model],
        )
      }
    )
  } else {
    text(fill: muted)[No LLM model data available.]
  }

  v(0.6em)

  // ══════════════════════════════════════════════════════════════════════
  // Appendix D: Methodology Notes
  // ══════════════════════════════════════════════════════════════════════
  heading(level: 2)[Appendix D: Methodology Notes]

  set text(size: 9.5pt)

  if suppress-praviar-branding {
    [The analysis system performs automated Freedom-to-Operate screening through the following stages:]
  } else {
    [The Praviar analysis pipeline performs automated Freedom-to-Operate screening through the following stages:]
  }

  v(0.2em)

	enum(
	  [*Chemical Resolution* -- The target compound is resolved to canonical SMILES, InChIKey, and associated identifiers using PubChem and other databases.],
	  [*Query Expansion* -- Multiple search strategies (structural, substructural, keyword, CPC classification) are generated to maximize recall.],
	  [*Multi-Source Patent Search* -- #patent-search-step],
	  [*Hard Filtering* -- Expired patents, non-relevant CPC classes, and duplicates are removed.],
	  [*Relevance Ranking* -- Remaining patents are scored using BM25 text similarity combined with structural similarity metrics.],
	  [*AI Triage* -- An LLM evaluates each patent's relevance to the target compound and filters to the most relevant subset.],
    [*Deep Analysis* -- Each triaged patent undergoes element-by-element claim analysis against the target compound.],
    [*Doctrine of Equivalents* -- For patents with "not met" elements, the function-way-result test is applied.],
    [*Invalidity Screening* -- Prior art references are evaluated for anticipation and obviousness potential.],
    [*Report Generation* -- Results are synthesized with verification checks and confidence assessments.],
  )

  v(0.3em)

  [*Important:* This automated screening identifies potential patent risks but cannot replace the judgment of a qualified patent attorney. Claim construction, prosecution history analysis, and legal strategy require human expertise.]

  v(0.6em)

  // ══════════════════════════════════════════════════════════════════════
  // Appendix E: Cost & Performance Summary
  // ══════════════════════════════════════════════════════════════════════
  heading(level: 2)[Appendix E: Cost & Performance Summary]

  // Token usage
  heading(level: 3)[Token Usage]

  table(
    columns: (1fr, auto),
    align: (left, right),
    stroke: 0.5pt + border,
    inset: 6pt,
    fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
    [*Total Input Tokens*], fmt-number(total-input),
    [*Total Output Tokens*], fmt-number(total-output),
    [*Total Tokens*], fmt-number(total-input + total-output),
    [*Estimated Cost*], fmt-usd(cost),
  )

  v(0.3em)

  // Per-step token breakdown
  if step-usage.len() > 0 {
    heading(level: 3)[Per-Step Token Breakdown]

    table(
      columns: (1.5fr, 1fr, auto, auto),
      align: (left, left, right, right),
      stroke: 0.5pt + border,
      inset: 5pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Step]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Model]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Input]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Output]],
      ),
      ..for usage in step-usage {
        let step-name = usage.at("step_name", default: "")
        let model-name = usage.at("model_name", default: "")
        let input-tok = usage.at("input_tokens", default: 0)
        let output-tok = usage.at("output_tokens", default: 0)
        (
          text(size: 8pt)[#step-name],
          text(font: font-mono, size: 7pt)[#model-name],
          text(size: 8pt)[#fmt-number(input-tok)],
          text(size: 8pt)[#fmt-number(output-tok)],
        )
      }
    )
    v(0.3em)
  }

  // Timing data
  if timing.len() > 0 {
    heading(level: 3)[Pipeline Timing]

    table(
      columns: (1.5fr, auto, auto, auto),
      align: (left, right, right, right),
      stroke: 0.5pt + border,
      inset: 5pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Step]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Duration]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Items In]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 7.5pt)[Items Out]],
      ),
      ..for step in timing {
        let name = step.at("step_name", default: "")
        let duration = step.at("duration_seconds", default: 0)
        let items-in = step.at("items_processed", default: 0)
        let items-out = step.at("items_output", default: 0)
        (
          text(size: 8pt)[#name],
          text(size: 8pt)[#fmt-duration(duration)],
          text(size: 8pt)[#fmt-number(items-in)],
          text(size: 8pt)[#fmt-number(items-out)],
        )
      }
    )

    // Total duration
    {
      let total-secs = timing.map(s => float(s.at("duration_seconds", default: 0))).sum()
      v(0.2em)
      text(size: 9pt)[*Total pipeline duration:* #fmt-duration(total-secs)]
    }
  }
}
