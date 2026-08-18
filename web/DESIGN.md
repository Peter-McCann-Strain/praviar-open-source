# Design System

## Project: Praviar — AI Patent Intelligence Platform

## Visual Theme & Atmosphere

Authoritative, data-dense, and precise. Inspired by the restraint of top enterprise SaaS systems and the evidentiary language of regulated pharma work: clean geometry, purposeful density, no decorative excess. The UI communicates scientific credibility, freedom-to-operate rigor, and premium judgment. Runtime is locked to the premium light palette for readability and trust. Landing and empty states can use rich evidence fields; dense dashboard and report workflows should stay quiet, structured, and scan-friendly. Trust and precision over playfulness. Every pixel earns its place.

## Color Palette & Roles — Forensic Teal + Clinical Copper

The canonical values live in `../brand/praviar-palette.json`. `src/app/globals.css`, export constants, email templates, docs config, and generated assets must stay aligned to that manifest. Do not hard-code palette values in components unless a browser/print/email limitation requires it. Use role tokens (`--brand-primary`, `--bg-surface`, `--text-secondary`, `--border-subtle`, `--surface-muted`, etc.) in implementation.

### Brand Palette

- Ink (#0B1F24) — Authority, deep evidence fields, mark sheet in light mode
- Forensic Teal (#0E6F68) — Primary actions, active states, links, evidence confidence
- Clinical Mint (#5FB7A6) — Evidence highlights, chart contrast, mark bands and strokes
- Clinical Copper (#B87333) — Premium value accent, caution, decision emphasis
- Paper (#F6F4EF) — Warm page base, print/export background, mark cutout
- Soft Mint (#D7ECE5) — Quiet evidence wash, mark stratum, low-risk backgrounds

### Premium Light Runtime

- Background: warm Paper (`--bg-base`) with Soft Mint evidence washes
- Text: Ink and muted blue-green hierarchy
- Primary: Forensic Teal (`--brand-primary`)
- Secondary accent: Clinical Copper (`--brand-secondary`)
- Borders: visible clinical green-gray borders, not generic gray

### Semantic Roles

- HIGH risk/error: Clinical Red, used sparingly for blocking risk
- MEDIUM/warning: Copper Depth, used for judgment/caution
- LOW/success: Deep Teal / Forensic Teal
- CLEAR/info: forensic teal/mint
- Charts: brand ring-segment palette first, semantic accents second

### Approved Tonal Ramp

- Deep Teal (`#0B4F4C`) — readable emphasis on Paper/Mint and support for axes, headings, and LOW-risk text
- Teal Hover (`#0B5F59`) and Teal Risk (`#0C766D`) — interaction/risk variants derived from Forensic Teal
- Copper Depth (`#8A4F1F`) — small warning/caution text; raw Clinical Copper is reserved for large numerals, borders, charts, and decorative accents
- Copper Emphasis (`#7A451B`) — high-contrast warning emphasis on light surfaces
- Evidence Muted (`#516F68`) — secondary metadata and quiet export text, never as a new brand colour
- Chart Mint (`#8ED7C9`) — export-only chart series tint derived from Clinical Mint, never small UI text
- Border roles (`#C8D8D2`, `#D9E3DE`, `#7FA69A`) — clinical green-gray separators and focusable emphasis
- Loading roles (`#E3ECE7`, `#F8F6F1`) — skeleton base/highlight only
- Inverted Hover (`#123238`) — hover state for Ink callout panels only
- Clinical Red (`#C2413A`, `#7F1D1D`) — blocking risk and errors only
- Washes (`#D7ECE5`, `#EAF6F2`, `#F7EEE5`, `#FDECEC`) — status backgrounds paired with text labels/icons; never rely on colour alone

## Typography Rules

Inter (variable) for all UI text. Geist Mono for SMILES strings, CAS numbers, patent identifiers, and code.

- Display XL: 36px, bold (700), tight tracking (-0.02em) — page titles
- Heading XL: 24px, semibold (600), tight tracking — section headers
- Heading MD: 18px, semibold (600) — card titles, tab labels
- Heading SM: 16px, semibold (600) — sub-section headers
- Label LG: 14px, medium (500) — form labels, table headers
- Label SM: 12px, medium (500), wide tracking (0.04em) — uppercase badges, metadata labels
- Body LG: 16px, regular (400) — primary body text, descriptions
- Body SM: 14px, regular (400) — secondary body text, table cells
- Caption: 12px, regular (400) — timestamps, helper text, footnotes
- Mono: Geist Mono, 13px — patent IDs (US10123456B2), SMILES (CC(=O)Oc1ccccc1C(=O)O), CAS numbers

## Component Stylings

### Buttons

Rounded-lg (8px radius). Primary: `--brand-primary` fill with paper/ink contrast handled by the component. Secondary: transparent with tokenized border. Destructive: semantic error emphasis. Ghost: transparent, text color only. All have smooth 150ms transition. Focus ring: 2px forensic teal offset.

### Cards

Rounded-lg (8px radius). App cards use tokenized surface, border, and shadow values. Avoid nested cards and floating page-section cards; use cards for repeated items, modals, and genuinely framed tools. Padding: 16-24px depending on density.

### Data Tables

Compact 40px rows. Sticky header row with slightly elevated background. Semi-transparent alternating row tints. Monospace font for patent IDs and SMILES. Risk badges as inline colored pills. Sort arrows on column headers. Horizontal scroll on overflow. 12px cell padding.

### Risk Badges

Pill shape (rounded-full). Compact (px-2 py-0.5, 12px text, medium weight).

- HIGH: Clinical Red background, accessible foreground
- MEDIUM: Copper Depth background, accessible foreground
- LOW: Teal-green background, accessible foreground
- CLEAR: Forensic teal/mint background, accessible foreground

### Status Badges

Pill shape. Outlined style with dot indicator.

- Running: Teal border, pulsing dot
- Completed: Teal-green border, solid dot
- Failed: Clinical Red border, solid dot
- Pending: Gray border, empty dot

### Sidebar Navigation

240px expanded, 64px collapsed (icon-only). Tokenized app chrome background. Nav items: 40px height, 8px radius, icon + label. Active item: teal-tinted background, primary text. Hover: subtle tokenized overlay. Collapsible with smooth 200ms transition. Bottom: user avatar with Clerk integration.

### Tabs

Underline or segmented style depending on density. Active tab: forensic teal treatment, primary text color. Inactive: secondary text. Hover: primary text color. Tabs scroll horizontally on overflow. 14px medium weight text.

### Input Fields

Rounded-lg (8px). Tokenized field background and border. 40px height minimum, 12px horizontal padding. Focus: 2px forensic teal ring. Placeholder: tertiary text color.

### Tooltips

Rounded-md (6px). Tokenized surface with Ink text and clear border contrast. 300ms show delay. Arrow pointing to target. Max-width 240px. 12px padding.

### Modals/Dialogs

Centered overlay. Rounded-lg (8px) unless an existing primitive requires otherwise. Tokenized dialog panel with premium glass/elevation. Max-width 480px for forms, 640px for detail views. Backdrop blur with semi-transparent overlay.

## Layout Principles

- 12-column responsive grid
- Collapsible left sidebar: 240px expanded, 64px collapsed (icon-only mode)
- Sticky top bar: 56px height, breadcrumbs + user menu + notification bell
- Content area: max-width 1440px, centered, 24px padding
- Dashboard KPI row: 4 cards in responsive grid (1 col mobile, 2 tablet, 4 desktop)
- Data tables: full available width, horizontal scroll on mobile
- Report tabs: full width below a persistent toolbar (search, export, share)
- Generous whitespace between sections (32px), tight within cards (16px)
- Page transitions: subtle 200ms fade-in on route change
- Staggered card animations: 50ms delay between siblings on initial load
