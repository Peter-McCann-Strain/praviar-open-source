export const PRINT_STYLES = `
@media print {
  /* Hide non-print elements */
  nav,
  .no-print,
  [data-no-print],
  button:not([data-print-trigger]):not([data-print-content]),
  .praviar-app-field > header,
  .praviar-app-field > aside,
  [aria-label="Workspace data boundary"],
  .praviar-sidebar-field,
  .sidebar,
  .topbar {
    display: none !important;
  }

  button[data-print-content] {
    display: flex !important;
    width: 100% !important;
    border: 0 !important;
    background: transparent !important;
    color: #0B1F24 !important;
    box-shadow: none !important;
    text-align: left !important;
  }

  /* Reset background and colors for printing */
  body {
    background: #F6F4EF !important;
    color: #0B1F24 !important;
    font-size: 11pt !important;
    line-height: 1.5 !important;
    margin: 0 !important;
  }

  .praviar-app-field,
  #main-content,
  .praviar-report-workspace {
    display: block !important;
    width: 100% !important;
    max-width: 100% !important;
    margin: 0 !important;
    padding: 0 !important;
    overflow: visible !important;
  }

  .print-report-wrapper {
    background: #F6F4EF !important;
    color: #0B1F24 !important;
    padding: 0 !important;
    margin: 0 !important;
    width: 100% !important;
    max-width: 100% !important;
    print-color-adjust: exact !important;
    -webkit-print-color-adjust: exact !important;
  }

  /* Ensure tables print correctly */
  table {
    border-collapse: collapse !important;
    width: 100% !important;
    font-size: 10pt !important;
  }

  th, td {
    border: 1px solid #D7ECE5 !important;
    padding: 6px 8px !important;
    text-align: left !important;
    color: #0B1F24 !important;
  }

  th {
    background: #D7ECE5 !important;
    font-weight: 600 !important;
  }

  /* Page break handling */
  .print-page-break {
    page-break-before: always;
  }

  .print-avoid-break {
    page-break-inside: avoid;
  }

  /*
   * Print is paged media, so its CSS viewport is narrower than the desktop
   * workspace even when the print was launched from a wide browser. Restore
   * the decision-oriented grids explicitly instead of inheriting the mobile
   * one-column layouts. This keeps one governed record legible and compact.
   */
  [data-testid="counsel-next-actions"] > div:first-child > div:nth-child(2) {
    grid-template-columns: minmax(0, 1.25fr) repeat(3, minmax(0, 0.55fr)) !important;
  }

  [data-testid="counsel-next-actions"] > ul {
    gap: 8px !important;
    padding: 10px 0 !important;
  }

  [data-testid="counsel-next-actions"] > ul > li {
    display: grid !important;
    grid-template-columns:
      minmax(7.5rem, 0.72fr)
      minmax(4.8rem, 0.38fr)
      minmax(6.5rem, 0.62fr)
      minmax(0, 1fr)
      minmax(6.5rem, 0.52fr) !important;
    break-inside: avoid-page !important;
    page-break-inside: avoid !important;
    overflow: visible !important;
  }

  [data-testid="counsel-next-actions"] > ul > li > div {
    border-bottom: 0 !important;
    border-right: 1px solid #D7ECE5 !important;
    padding: 8px !important;
  }

  [data-testid="counsel-next-actions"] > ul > li > div:last-child {
    border-right: 0 !important;
  }

  [data-testid="counsel-next-actions"] > ul > li > div:nth-child(3) button {
    display: inline-flex !important;
    min-height: 0 !important;
    width: auto !important;
    padding: 2px 4px !important;
    font-size: 7pt !important;
  }

  [data-testid="claim-decision-matrix"] [aria-label="Filter claim elements"],
  [data-testid="claim-decision-matrix"]
    dl[aria-label="Claim review queue summary"],
  [data-testid="claim-decision-matrix"] > p[role="status"] > span {
    display: none !important;
  }

  [data-testid="claim-decision-matrix"] > header {
    padding: 10px 12px !important;
  }

  [data-testid="claim-decision-matrix"] > p[role="status"] {
    padding: 7px 12px !important;
  }

  [data-claim-coordinate] {
    break-inside: auto !important;
    page-break-inside: auto !important;
  }

  [data-claim-coordinate] > details > [data-print-claim-layers] {
    display: grid !important;
    grid-template-columns: minmax(0, 1fr) !important;
    gap: 10px !important;
    padding: 0 12px 12px !important;
  }

  [data-print-claim-coordinate-header] {
    display: block !important;
    border-bottom: 1px solid #D7ECE5 !important;
    margin: 0 0 7px !important;
    padding: 0 0 7px !important;
  }

  [data-claim-coordinate] > details > [data-print-claim-layers] > section,
  [data-claim-coordinate] article,
  [data-claim-coordinate] blockquote,
  [data-claim-coordinate] dl > div {
    break-inside: avoid-page !important;
    page-break-inside: avoid !important;
  }

  [data-claim-coordinate] > details > [data-print-claim-layers] > section {
    padding: 10px !important;
  }

  [data-claim-coordinate] article {
    padding: 7px !important;
  }

  [data-claim-coordinate] details,
  [data-claim-coordinate] article,
  [data-claim-coordinate] section {
    overflow: visible !important;
  }

  /*
   * Browser print retains the desktop responsive viewport while paginating
   * into a much narrower sheet. Collapse the evidence verifier to one
   * readable column so no citation, source excerpt, or deterministic result
   * can be clipped beyond the printable edge.
   */
  [data-print-citation-verifier-grid] {
    grid-template-columns: minmax(0, 1fr) !important;
  }

  [data-print-verification-checks-grid] {
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
  }

  /* Keep charts with their headings and prevent a short chart from becoming
     an otherwise empty trailing page. */
  .print-report-wrapper .recharts-responsive-container {
    height: 175px !important;
    min-height: 160px !important;
    max-height: 175px !important;
  }

  .print-report-wrapper .recharts-wrapper,
  .print-report-wrapper .recharts-surface {
    max-height: 175px !important;
  }

  /* Search controls are useful in the live evidence workspace but are not
     report evidence. Keep the governed ledger in the packet and omit the
     interactive query surface from the static artifact. */
  [data-testid="report-tab-evidence"]
    div.space-y-4:has(
      > div.praviar-surface-premium
        form
        input[aria-label="Evidence search query"]
    ) {
    display: none !important;
  }

  [aria-label="Evidence workbench findings table"] table {
    display: table !important;
    width: 100% !important;
    min-width: 0 !important;
    table-layout: fixed !important;
  }

  [aria-label="Evidence workbench findings table"] th:last-child,
  [aria-label="Evidence workbench findings table"] td:last-child {
    display: none !important;
  }

  [aria-label="Evidence workbench findings table"] th:nth-child(1),
  [aria-label="Evidence workbench findings table"] td:nth-child(1) {
    width: 24% !important;
  }

  [aria-label="Evidence workbench findings table"] th:nth-child(2),
  [aria-label="Evidence workbench findings table"] td:nth-child(2) {
    width: 14% !important;
  }

  [aria-label="Evidence workbench findings table"] th:nth-child(3),
  [aria-label="Evidence workbench findings table"] td:nth-child(3) {
    width: 28% !important;
  }

  [aria-label="Evidence workbench findings table"] th:nth-child(4),
  [aria-label="Evidence workbench findings table"] td:nth-child(4) {
    width: 34% !important;
  }

  /* Meta is a dense ledger of small, atomic records. Tighten only its print
     rhythm so the disclaimer stays with the metadata instead of becoming an
     orphaned trailing sheet. */
  #tabpanel-meta .space-y-6 > * + * {
    margin-top: 10px !important;
  }

  [data-print-keep-together] {
    break-inside: avoid-page !important;
    page-break-inside: avoid !important;
  }

  /* The governed matrix already prints every exact claim coordinate. Keep the
     optional on-screen narrative out of the same packet to avoid duplicating
     each claim and inflating the PDF with state-dependent pages. */
  [data-print-redundant-narrative] {
    display: none !important;
  }

  [data-print-redundant-disclaimer] {
    display: none !important;
  }

  /* Ensure charts and figures render */
  svg {
    max-width: 100% !important;
    height: auto !important;
  }

  /* Links: show URL after text */
  a[href]:after {
    content: " (" attr(href) ")";
    font-size: 9pt;
    color: #0E6F68;
  }

  a[href^="#"]:after,
  a[href^="javascript"]:after {
    content: "" !important;
  }

  /* Badges and indicators */
  .badge, [class*="badge"] {
    border: 1px solid #D7ECE5 !important;
    background: #F6F4EF !important;
    color: #0B1F24 !important;
  }

  /* Print header */
  .print-header {
    display: flex !important;
    flex-wrap: wrap !important;
    border-bottom: 2px solid #0E6F68;
    padding-bottom: 8px;
    margin-bottom: 9px;
  }

  .print-header > * {
    max-width: 100% !important;
    min-width: 0 !important;
  }

  .print-footer {
    display: block !important;
    position: static !important;
    margin: 4px 0 0 !important;
    padding: 4px 0 0 !important;
    background: #F6F4EF !important;
    color: #0B1F24 !important;
    font-size: 7pt !important;
    line-height: 1.25 !important;
    break-inside: avoid-page !important;
    page-break-inside: avoid !important;
  }

  .print-footer p {
    margin: 0 !important;
    font-size: 7pt !important;
    line-height: 1.25 !important;
  }

  .print-provenance-strip {
    display: block !important;
    border: 1px solid #D7ECE5 !important;
    border-left: 4px solid #B87333 !important;
    background: #F6F4EF !important;
    margin: 0 0 12px !important;
    padding: 8px 10px !important;
    page-break-inside: avoid;
  }

  .print-claimed-use-receipts {
    display: block !important;
    margin: 0 0 12px !important;
    page-break-inside: auto !important;
  }

  .print-claimed-use-receipts article {
    break-inside: avoid-page !important;
    page-break-inside: avoid !important;
  }

  .print-packet-summary {
    display: grid !important;
    grid-template-columns: minmax(0, 1.1fr) minmax(0, 1.4fr) !important;
    gap: 8px !important;
    border: 1px solid #B8DCD2 !important;
    border-left: 4px solid #0E6F68 !important;
    background: #F8FBF8 !important;
    margin: 0 0 8px !important;
    padding: 8px 10px !important;
    page-break-inside: avoid;
  }

  .print-packet-summary-ready {
    border-left-color: #0E6F68 !important;
    background: #EFF8F4 !important;
  }

  .print-packet-summary-warning {
    border-left-color: #8A4F1F !important;
    background: #FFF9ED !important;
  }

  .print-packet-summary-danger {
    border-left-color: #C2413A !important;
    background: #FFF1F0 !important;
  }

  .print-packet-summary-neutral {
    border-left-color: #0E6F68 !important;
  }

  .print-packet-summary-status {
    min-width: 0 !important;
  }

  .print-packet-summary-kicker {
    color: #0E6F68 !important;
    font-size: 7.5pt !important;
    font-weight: 800 !important;
    letter-spacing: 0.12em !important;
    margin: 0 0 4px !important;
    text-transform: uppercase !important;
  }

  .print-packet-summary-label {
    color: #0B1F24 !important;
    font-size: 12pt !important;
    font-weight: 800 !important;
    line-height: 1.2 !important;
    margin: 0 0 4px !important;
    overflow-wrap: anywhere !important;
  }

  .print-packet-summary-detail {
    color: #516F68 !important;
    font-size: 8.4pt !important;
    line-height: 1.35 !important;
    margin: 0 !important;
    overflow-wrap: anywhere !important;
  }

  .print-packet-summary-grid {
    display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    gap: 7px 10px !important;
    margin: 0 !important;
  }

  .print-packet-summary-item {
    min-width: 0 !important;
  }

  .print-packet-summary-item-label {
    color: #516F68 !important;
    font-size: 7pt !important;
    font-weight: 800 !important;
    letter-spacing: 0.08em !important;
    margin: 0 0 3px !important;
    text-transform: uppercase !important;
  }

  .print-packet-summary-item-value {
    color: #0B1F24 !important;
    font-size: 8.6pt !important;
    font-weight: 700 !important;
    line-height: 1.3 !important;
    margin: 0 !important;
    overflow-wrap: anywhere !important;
  }

  .print-reliance-banner {
    display: block !important;
    border: 1px solid #B87333 !important;
    background: #FFF9ED !important;
    margin: 0 0 8px !important;
    padding: 8px 10px !important;
    page-break-inside: avoid;
  }

  .print-reliance-title {
    color: #7A4E16 !important;
    font-size: 7.5pt !important;
    font-weight: 800 !important;
    letter-spacing: 0.12em !important;
    margin: 0 0 7px !important;
    text-transform: uppercase !important;
  }

  .print-reliance-grid {
    display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    gap: 8px !important;
  }

  .print-reliance-item {
    min-width: 0 !important;
  }

  .print-reliance-label {
    color: #7A4E16 !important;
    font-size: 7pt !important;
    font-weight: 800 !important;
    letter-spacing: 0.08em !important;
    margin: 0 0 3px !important;
    text-transform: uppercase !important;
  }

  .print-reliance-value {
    color: #0B1F24 !important;
    font-size: 8.2pt !important;
    line-height: 1.35 !important;
    margin: 0 !important;
    overflow-wrap: anywhere !important;
  }

  .print-provenance-kicker {
    color: #0E6F68 !important;
    font-size: 7.5pt !important;
    font-weight: 700 !important;
    letter-spacing: 0.12em !important;
    margin: 0 0 7px !important;
    text-transform: uppercase !important;
  }

  .print-provenance-grid {
    display: grid !important;
    grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
    gap: 8px !important;
  }

  .print-provenance-item {
    border-right: 1px solid #D7ECE5 !important;
    min-width: 0 !important;
    padding-right: 8px !important;
  }

  .print-provenance-item:last-child {
    border-right: 0 !important;
    padding-right: 0 !important;
  }

  .print-provenance-label {
    color: #516F68 !important;
    font-size: 7.5pt !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    margin: 0 0 3px !important;
    text-transform: uppercase !important;
  }

  .print-provenance-value {
    color: #0B1F24 !important;
    font-size: 9.5pt !important;
    font-weight: 700 !important;
    margin: 0 0 2px !important;
    overflow-wrap: anywhere !important;
  }

  .print-provenance-detail {
    color: #516F68 !important;
    font-size: 8pt !important;
    line-height: 1.35 !important;
    margin: 0 !important;
    overflow-wrap: anywhere !important;
  }

  /* Print footer */
  @page {
    margin: 1.5cm;
    size: letter;
  }

  /* Remove shadows and rounded corners */
  * {
    box-shadow: none !important;
    text-shadow: none !important;
  }
}

@media print and (max-width: 640px) {
  .print-header {
    display: block !important;
  }

  .print-packet-summary,
  .print-packet-summary-grid,
  .print-reliance-grid,
  .print-provenance-grid {
    grid-template-columns: 1fr !important;
  }

  .print-provenance-item {
    border-right: 0 !important;
    border-bottom: 1px solid #D7ECE5 !important;
    padding-bottom: 6px !important;
    padding-right: 0 !important;
  }

  .print-provenance-item:last-child {
    border-bottom: 0 !important;
    padding-bottom: 0 !important;
  }
}

/* Hide print header in screen mode */
@media screen {
  .print-header,
  .print-footer,
  .print-packet-summary,
  .print-reliance-banner,
  .print-provenance-strip {
    display: none;
  }

  .print-claimed-use-receipts {
    display: none;
  }
}
`;
