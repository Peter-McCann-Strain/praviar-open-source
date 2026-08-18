// Praviar Pipeline FTO Report — Main Orchestrator
// Compiles a complete Freedom-to-Operate analysis report from JSON data.
//
// Inputs (passed via `typst compile --input`):
//   data-path     Path to report.json (serialized FTOReport)
//   assets-dir    Directory containing pre-rendered chart PNGs and structure SVGs
//   branding-path Path to branding.json (serialized BrandingConfig)
//   export-options-path Path to normalized export scope/audience JSON

// ── Library Imports ────────────────────────────────────────────────────────

#import "lib/colors.typ"
#import "lib/typography.typ": apply-typography
#import "lib/layout.typ": apply-layout
#import "lib/risk-badge.typ"
#import "lib/utils.typ"

// ── Component Imports ──────────────────────────────────────────────────────

#import "components/cover.typ": render-cover
#import "components/toc.typ": render-toc
#import "components/coverage.typ": render-coverage
#import "components/executive.typ": render-executive
#import "components/blocker-families.typ": render-blocker-families
#import "components/compound.typ": render-compound
#import "components/methodology.typ": render-methodology
#import "components/landscape.typ": render-landscape
#import "components/risk-matrix.typ": render-risk-matrix
#import "components/patent-detail.typ": render-patent-details
#import "components/drawings.typ": render-drawings
#import "components/recommendations.typ": render-recommendations
#import "components/verification.typ": render-verification
#import "components/appendices.typ": render-appendices
#import "components/manifest.typ": render-manifest
#import "components/reviewer_decisions.typ": reviewer-decisions-section
#import "components/disclaimer.typ": render-disclaimer

// ── Load Data ──────────────────────────────────────────────────────────────

#let data-path = sys.inputs.at("data-path")
#let assets-dir = sys.inputs.at("assets-dir")
#let branding-path = sys.inputs.at("branding-path")
#let export-options-path = sys.inputs.at("export-options-path")

#let data = json(data-path)
#let branding = json(branding-path)
#let export-options = json(export-options-path)
#let export-sections = export-options.at("sections", default: ())
#let include-section(section-id) = export-sections.contains(section-id)
#let blocker-families = data.at("clearance_decision", default: (:)).at("decision_audit", default: (:)).at("blocker_families", default: ())
#let document-compound = data.at("compound", default: (:)).at("name", default: "Unknown compound")
#let document-author = branding.at("display_name", default: "Praviar")

// ── Apply Document Configuration ───────────────────────────────────────────

#set document(
  title: [Freedom-to-Operate Analysis - #document-compound],
  author: (str(document-author),),
  description: [Patent screening evidence packet with provenance and reliance boundaries.],
  keywords: ("freedom to operate", "patent analysis", "chemical structure", "evidence"),
  date: none,
)
#set text(lang: "en")

// Typography: fonts, heading styles, paragraph spacing
#show: apply-typography

// Page layout: margins, headers, footers
#show: apply-layout.with(branding: branding)

// ── Document Body ──────────────────────────────────────────────────────────

// 1. Cover page
#render-cover(data, branding, assets-dir)

// 2. Table of contents
#render-toc()

// 3. Search coverage banner (source-health surface — SG-111).
//    Attorneys must see coverage gaps before reading findings.
#render-coverage(data)

// 4. Executive summary with risk verdict
#if include-section("executive_summary") {
  render-executive(data, assets-dir)
  pagebreak()
  if blocker-families.len() > 0 {
    render-blocker-families(data)
    pagebreak()
  }
}

// 4. Compound profile
#if include-section("patent_analysis") {
  render-compound(data, assets-dir)
  pagebreak()

  // 5. Search methodology and data sources
  render-methodology(data, assets-dir)

  pagebreak()

  // 6. Patent landscape overview (charts)
  render-landscape(data, assets-dir)

  pagebreak()

  // 7. Risk matrix — summary table of all patents
  render-risk-matrix(data)

  // 7.5. Chemical structure analysis from patent drawings
  render-drawings(data, assets-dir)
}

// 8. Detailed patent analysis (HIGH and MEDIUM only)
#if include-section("patent_analysis") or include-section("claim_charts") or include-section("invalidity_assessment") {
  render-patent-details(data, assets-dir, export-options)
}

// 9. Recommendations and action items
#if include-section("executive_summary") {
  render-recommendations(data)
  pagebreak()
}

// 10. Verification, quality checks, model attribution
#if include-section("audit_trail") {
  render-verification(data)
  pagebreak()
}

// 11. Appendices (full listing, search params, models, methodology, cost)
#if include-section("pipeline_metadata") {
  render-appendices(data, branding)

  // 11.5. Run provenance manifest (auditor appendix)
  render-manifest(data)
}

// 11.6. Reviewer decisions appendix (SG-reviewer / WS-3) — LAST appendix so
// attorney accept/reject/edit decisions are the final thing a reader sees
// before the disclaimer.
// Scoped equivalent of the previous top-level #reviewer-decisions-section(data)
#if include-section("audit_trail") {
  reviewer-decisions-section(data)
}

// 12. Back page disclaimer
#render-disclaimer(data, branding)
