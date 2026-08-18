// Praviar Pipeline Compound Profile

#import "../lib/colors.typ": ink, deep-teal, muted, border, surface
#import "../lib/typography.typ": font-heading, font-body, font-mono, font-table

// ── Internal: Properties Table ─────────────────────────────────────────────

#let _properties_table(name, smiles, inchi-key, formula, mw, cas, groups) = {
  set text(size: 9.5pt)

  let cas-str = if cas.len() > 0 { cas.join(", ") } else { "Not available" }
  let groups-str = if groups.len() > 0 { groups.join(", ") } else { "Not identified" }
  let mw-str = if mw != none { str(calc.round(float(mw), digits: 2)) + " g/mol" } else { "N/A" }

  table(
    columns: (auto, 1fr),
    align: (right, left),
    stroke: 0.5pt + border,
    fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
    inset: 6pt,
    [*Compound Name*], text(weight: "bold")[#name],
    [*Molecular Formula*], if formula != none { formula } else { "N/A" },
    [*Molecular Weight*], mw-str,
    [*InChIKey*], if inchi-key != none { text(font: font-mono, size: 8pt)[#inchi-key] } else { "N/A" },
    [*CAS Numbers*], cas-str,
    [*Functional Groups*], groups-str,
  )
}

#let render-compound(data, assets-dir) = {
  let compound = data.at("compound", default: (:))
  let name = compound.at("name", default: "Unknown")
  let smiles = compound.at("canonical_smiles", default: none)
  let inchi-key = compound.at("inchi_key", default: none)
  let formula = compound.at("molecular_formula", default: none)
  let mw = compound.at("molecular_weight", default: none)
  let cas = compound.at("cas_numbers", default: ())
  let groups = compound.at("functional_groups", default: ())
  let related = compound.at("related_compounds", default: ())

  heading(level: 1)[Compound Profile]

  // ── Structure Image + Properties Side by Side ──────────────────────────
  {
    let has-structure = data.at("_has_structure_image", default: false)

    if has-structure {
      grid(
        columns: (1fr, 1.2fr),
        column-gutter: 16pt,
        align: (center + horizon, left),
        // Structure image
        block(
          stroke: 0.5pt + border,
          radius: 4pt,
          inset: 8pt,
          fill: surface,
        )[
          #image(
            assets-dir + "/target_structure.svg",
            width: 100%,
            alt: "Two-dimensional chemical structure of " + name,
          )
        ],
        // Properties
        _properties_table(name, smiles, inchi-key, formula, mw, cas, groups),
      )
    } else {
      _properties_table(name, smiles, inchi-key, formula, mw, cas, groups)
    }
  }

  v(0.6em)

  // ── SMILES (full, in monospace block) ──────────────────────────────────
  if smiles != none {
    heading(level: 2)[Canonical SMILES]
    block(
      width: 100%,
      fill: surface,
      radius: 3pt,
      inset: 8pt,
      stroke: 0.5pt + border,
    )[
      #set text(font: font-mono, size: 8pt)
      #smiles
    ]
    v(0.4em)
  }

  // ── Related Compounds ──────────────────────────────────────────────────
  if related.len() > 0 {
    heading(level: 2)[Related Compounds]

    table(
      columns: (auto, 1fr, auto),
      align: (left, left, center),
      stroke: 0.5pt + border,
      fill: (_, row) => if calc.rem(row, 2) == 0 { surface } else { surface },
      // Header
      table.header(
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Name]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[SMILES]],
        table.cell(fill: ink)[#text(fill: surface, weight: "bold")[Relationship]],
      ),
      // Rows
      ..for compound-item in related {
        let c-name = compound-item.at("name", default: "N/A")
        let c-smiles = compound-item.at("canonical_smiles", default: "N/A")
        let c-rel = compound-item.at("relationship", default: "")
        (
          c-name,
          text(font: font-mono, size: 7.5pt)[#c-smiles],
          c-rel,
        )
      }
    )
  }
}
