// Praviar Pipeline Run Provenance — Report Manifest appendix
// Compact table of how the run was produced (git SHA, prompt hashes, models,
// sampling params, source snapshots, tool-definition hashes, and tool-trace
// digest). Auditors only — attorneys can skip this page.

#import "../lib/colors.typ": ink, border, surface
#import "../lib/typography.typ": font-mono

#let render-manifest(data) = {
  let manifest = data.at("manifest", default: none)
  if manifest == none {
    return
  }

  pagebreak()
  heading(level: 1)[Run Provenance]

  text(size: 9pt)[
    This appendix pins down exactly how this report was generated so it can be
    audited and re-played. Each value is the runtime fingerprint at the moment
    of report finalization.
  ]

  v(0.5em)

  // ── Top-level fields ────────────────────────────────────────────────────
  let pipeline-version = manifest.at("pipeline_version", default: "unknown")
  let generated-at = manifest.at("generated_at", default: "")
  let compound-query = manifest.at("compound_query", default: "")
  let tool-digest = manifest.at("tool_trace_digest", default: "")
  let tool-call-count = manifest.at("tool_call_count", default: 0)

  set text(size: 8.5pt)
  table(
    columns: (auto, 1fr),
    align: (left, left),
    stroke: 0.5pt + border,
    inset: 5pt,
    fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
    table.header(
      table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Field]],
      table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Value]],
    ),
    [Pipeline version (git SHA)], text(font: font-mono)[#pipeline-version],
    [Generated at (UTC)], text(font: font-mono)[#generated-at],
    [Compound query], text(font: font-mono)[#compound-query],
    [Tool-trace digest (SHA256)], text(font: font-mono, size: 7pt)[#tool-digest],
    [Tool calls captured], text(font: font-mono)[#repr(tool-call-count)],
  )

  // ── Tool definition hashes ──────────────────────────────────────────────
  let tool-definition-hashes = manifest.at("tool_definition_hashes", default: (:))
  if tool-definition-hashes.len() > 0 {
    v(0.5em)
    heading(level: 2)[Tool Definition Hashes (SHA256)]
    set text(size: 7pt)
    table(
      columns: (auto, 1fr),
      align: (left, left),
      stroke: 0.5pt + border,
      inset: 4pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 8pt)[Tool]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 8pt)[SHA256]],
      ),
      ..for (tool-name, digest) in tool-definition-hashes {
        (text(font: font-mono)[#tool-name], text(font: font-mono)[#digest])
      }
    )
  }

  // ── Model versions ──────────────────────────────────────────────────────
  let models = manifest.at("model_versions", default: (:))
  if models.len() > 0 {
    v(0.5em)
    heading(level: 2)[Model Versions]
    table(
      columns: (auto, 1fr),
      align: (left, left),
      stroke: 0.5pt + border,
      inset: 5pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Role]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Model ID]],
      ),
      ..for (role, model) in models {
        ([#role], text(font: font-mono)[#model])
      }
    )
  }

  // ── Sampling parameters ─────────────────────────────────────────────────
  let sampling = manifest.at("sampling", default: (:))
  if sampling.len() > 0 {
    v(0.5em)
    heading(level: 2)[Sampling Parameters]
    table(
      columns: (auto, 1fr),
      align: (left, left),
      stroke: 0.5pt + border,
      inset: 5pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Role]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Parameters]],
      ),
      ..for (role, params) in sampling {
        let pretty = ()
        for (k, v) in params {
          pretty.push(k + "=" + repr(v))
        }
        ([#role], text(font: font-mono)[#pretty.join(", ")])
      }
    )
  }

  // ── Source snapshots ────────────────────────────────────────────────────
  let snapshots = manifest.at("source_snapshots", default: (:))
  if snapshots.len() > 0 {
    v(0.5em)
    heading(level: 2)[Source Snapshots]
    table(
      columns: (auto, 1fr),
      align: (left, left),
      stroke: 0.5pt + border,
      inset: 5pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Source]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Snapshot]],
      ),
      ..for (source, snap) in snapshots {
        ([#source], text(font: font-mono, size: 7.5pt)[#snap])
      }
    )
  }

  // ── Prompt hashes ───────────────────────────────────────────────────────
  let prompt-hashes = manifest.at("prompt_hashes", default: (:))
  if prompt-hashes.len() > 0 {
    v(0.5em)
    heading(level: 2)[Prompt Hashes (SHA256)]
    set text(size: 7pt)
    table(
      columns: (auto, 1fr),
      align: (left, left),
      stroke: 0.5pt + border,
      inset: 4pt,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 8pt)[Prompt File]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold", size: 8pt)[SHA256]],
      ),
      ..for (filename, digest) in prompt-hashes {
        (text(font: font-mono)[#filename], text(font: font-mono)[#digest])
      }
    )
  }
}
