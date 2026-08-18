# Praviar Pipeline — Technical Documentation

> **Praviar Pipeline** is a research pipeline for constructing counsel-review patent evidence around chemical compounds. Given a compound identifier (name, SMILES, CAS, InChI, or InChIKey), it attempts source retrieval, LLM-assisted triage and claim analysis, Doctrine of Equivalents and invalidity screening, deterministic consistency checks, and structured report assembly. Its output is not a legal opinion, does not establish freedom to operate, and has no validated public legal-accuracy result.

---

## Table of Contents

1. [Architecture Overview](#1-architecture-overview)
2. [Pipeline Flow Diagram](#2-pipeline-flow-diagram)
3. [Unified Adaptive Execution](#3-unified-adaptive-execution)
4. [Step 1 — Compound Resolution and Query Expansion](#4-step-1--compound-resolution-and-query-expansion)
5. [Step 2 — Multi-Source Patent Search and Ranking Funnel](#5-step-2--multi-source-patent-search-and-ranking-funnel)
6. [Step 3 — LLM Triage](#6-step-3--llm-triage)
7. [Step 4 — Claim Analysis](#7-step-4--claim-analysis)
8. [Step 5 — Doctrine of Equivalents](#8-step-5--doctrine-of-equivalents)
9. [Step 6 — Invalidity Screening](#9-step-6--invalidity-screening)
10. [Step 7 — Deterministic Verification](#10-step-7--deterministic-verification)
11. [Step 8 — Report Generation](#11-step-8--report-generation)
12. [Runtime Orchestration Layer](#12-runtime-orchestration-layer)
13. [Decisioning and Evidence Graph Layer](#13-decisioning-and-evidence-graph-layer)
14. [Data Model Reference](#14-data-model-reference)
15. [External Clients](#15-external-clients)
16. [Configuration Reference](#16-configuration-reference)
17. [Prompt Templates](#17-prompt-templates)
18. [API Layer](#18-api-layer)
19. [Error Handling Philosophy](#19-error-handling-philosophy)

---

## 1. Architecture Overview

```
User Input (compound name/SMILES/CAS/InChI)
    |
    v
[Step 1]  Compound Resolution ........... PubChem + RDKit
    |
    v
[Step 1b] Query Expansion ............... Claude Haiku + Tavily web search
    |
    v
[Step 2]  Multi-Source Patent Search .... PubChem SDQ, SureChEMBL, BigQuery,
    |                                     PatCID, EPO OPS, USPTO ODP
    |                                     (optional iterative search loop)
    v
[Step 2b] Patent Ranking Funnel ......... Hard filters -> Composite -> BM25
    |                                     (-> optional SPECTER2 embeddings)
    v
[Step 2c] Family Expansion .............. Broadest-claims selection per family
    |
    v
[Step 3]  LLM Triage .................... Claude Haiku (batched)
    |
    v
[Step 2d] Drawing Analysis .............. post-triage, gated computer vision
    |                                     (configured segmentation + ensemble OCSR)
    |                                     with Tanimoto/substructure evidence
    v
[Step 4]  Claim Analysis ................ world_class_adaptive:
    |                                     single-pass analysis, evaluator,
    |                                     automatic agentic escalation
    v
[Step 4b] Portfolio Critic .............. optional when enabled and analyses exist
    |
    v
[Step 5]  Doctrine of Equivalents ....... USPTO file wrapper + Claude Sonnet
    |
    v
[Step 6]  Invalidity Screening .......... PTAB API, Semantic Scholar, OpenAlex,
    |                                     BigQuery + Claude Sonnet
    v
[Step 7]  Deterministic Verification .... 10 rule-based checks (no LLM)
    |
    v
[Step 8]  Report Generation ............. Unified multi-stage pipeline;
    |                                     initial non-vision matter evidence index
    v
[Review brief] Integrity binding ........ prompt hashes + exact source-span map;
    |                                     bounded risk/summary/ledger-count brief
    v
[REPORT_REVIEW] Human checkpoint ........ blocking only when configured;
    |                                     web approval attests to brief + SHA-256
    v
[Finalization] Clearance Decisioning .... attach_report_runtime_metadata;
    |                                     rebuild non-vision evidence index,
    |                                     coverage, jurisdiction and outcome gates
    v
FTOReport (JSON / Markdown / PDF) ........ manifest + output after decision metadata
```

**Key Design Principles:**
- **Async throughout** — every I/O operation uses `async`/`await`
- **No silent evidence fallback** — required-evidence failures propagate; explicitly optional paths are configured and recorded
- **Central runtime policy** — operator-controlled thresholds, weights, and limits live in validated `Settings`; schema and algorithm constants remain in code
- **Structured logging** — `structlog` with structured key-value pairs at every decision point
- **Pydantic validation** — all inputs and outputs are validated Pydantic models with strict `extra="forbid"`
- **LLM output coercion** — validators normalise case, handle "yes"/"true"/"1" -> `True`, map synonyms
- **Deterministic where possible** — LLM is used for judgement calls; everything else is rule-based
- **Checkpoint-aware orchestration** — completed resumable stages save checkpoints; failed runs resume only from a compatible completed stage

**Technology Stack:**
- Python 3.11+, asyncio, Pydantic v2, pydantic-settings
- LLM: Anthropic Claude (Haiku for triage/query expansion/evaluation, Sonnet/Opus-class models for adaptive claim analysis, report narratives, and agentic escalation)
- Chemistry: RDKit (fingerprints, SMARTS matching, SMILES validation), MolDet/MolScribe/MolSight/MolNexTR/MolGrapher-compatible OCSR components governed by production-evidence gates
- Search: BM25s (lexical re-ranking), optional SPECTER2 (semantic re-ranking)
- Rendering: Typst (PDF), Matplotlib (charts), Markdown
- Rate limiting: `aiolimiter.AsyncLimiter`
- Retry: `tenacity` with exponential backoff

---

## 2. Pipeline Flow Diagram

```
                    ResolvedCompound + ExpandedQueries
                                 |
            +--------------------+--------------------+
            |                                         |
      search_patents (+ optional search loop)   (compound context
            |                                    passed to all
            v                                    downstream steps)
  (PatentHit[], SourceHealth,                         |
   SearchFunnelEntry[])                               |
            |                                         |
      rank_patents -> family_expansion                |
      -> drawing_analysis                             |
            |                                         |
            v                                         |
    ranked PatentHit[]                                |
            |                                         |
      triage_patents  <--------------------------------+
            |
            v
    TriageResult[] (RELEVANT + POSSIBLY_RELEVANT only)
            |
      run_world_class_claim_analysis  <----- BigQuery (claims enrichment)
      (single-pass first; agentic escalation when signals require it)
            |
            v
    PatentAnalysis[] (with element-by-element breakdown)
            |
      review_analyses (Step 4b: portfolio critic)
            |
     +------+------+
     |             |
assess_equivalents |
     |       assess_invalidity
     v             |
DoEAssessment[]    v
     |      InvalidityAssessment[]
     |             |
     +------+------+
            |
      verify_analysis  (deterministic, no LLM)
            |
            v
    VerificationResult (10 checks)
            |
      generate_report  (unified five-stage agentic pipeline)
            |
            v
        FTOReport
            |
      build_clearance_outputs  (post-report decisioning layer)
            |
            v
    ClearanceDecision, MatterGraph, EvidenceIndex
```

---

## 3. Unified Adaptive Execution

Praviar now has one backend execution profile: `world_class_adaptive`. Public `pipeline_mode`, `claim_analysis_depth`, `--mode`, `--depth`, and `report_pipeline_v2` controls have been removed from API schemas, runtime config, CLI args, org defaults, and checkpoint metadata. Requests or flags that still send those fields are rejected as invalid input rather than translated.

The former fast and agentic behaviors are preserved as internal stages:

| Stage | Behavior |
|-------|----------|
| Single-pass stage | Every patent starts with deterministic context assembly, enriched claims/prosecution/spec evidence, one structured claim-analysis call with extended thinking, and a Haiku evaluator pass. |
| Agentic escalation stage | The pipeline escalates into `ClaimAnalysisAgent` with tool access for specification lookup, claim-term construction, prosecution context, reasoning traces, and optional perspectives. |
| Adaptive reviewer | Step 4b uses a compact portfolio review for simple portfolios and agentic critic behavior for dense, high-risk, uncertain, or reviewer-critical portfolios. |
| Unified report | Step 8 always uses the five-stage agentic report generator and stamps report metadata with `world_class_adaptive`. |

Escalation is automatic and auditable. Signals include high-risk triage, dense patent sets, poor evaluator quality, uncertainty, weak source health, drawing evidence, Markush ambiguity, reviewer-critical findings, and runtime-global escalation reasons. `PatentAnalysis` records `analysis_execution_profile`, `analysis_stage`, `analysis_escalated`, and `analysis_escalation_reasons`; these are audit metadata, not user-selectable modes.

The iterative search loop remains an operational capability (`search_loop_enabled`) and may be turned on by adaptive runtime signals, but it is not a mode selector.

---

## 4. Step 1 — Compound Resolution and Query Expansion

### Step 1 — Compound Resolution

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step1_resolve.py`
**Entry point:** `async def resolve_compound(user_input: str) -> ResolvedCompound`

Resolves arbitrary user input into a fully characterised chemical compound with structural fingerprints, synonyms, and related compounds.

**Algorithm:**

1. **Input type detection** — regex-based heuristic:
   - CAS: `^\d{2,7}-\d{2}-\d$`
   - InChI: `^InChI=`
   - InChIKey: `^[A-Z]{14}-[A-Z]{10}-[A-Z]$`
   - SMILES: no spaces, 3+ chars, subset of valid SMILES characters, contains atom chars
   - Default: compound name

2. **PubChem resolution** — appropriate API call based on input type:
   - Name/CAS -> `resolve_by_name()`
   - SMILES -> `resolve_by_smiles()`
   - InChIKey -> `resolve_by_inchikey()`
   - InChI -> RDKit conversion to InChIKey -> `resolve_by_inchikey()`

3. **Synonym extraction** — `get_synonyms(cid)`, CAS numbers filtered via regex

4. **RDKit fingerprints:**
   - Morgan (ECFP4, radius=2, 2048 bits) — for Tanimoto similarity
   - MACCS keys (166 bits) — for structural alerts
   - 15 functional groups via SMARTS: carboxylic acid, amine, alcohol, ester, amide, ketone, aldehyde, ether, phenol, nitrile, phosphate, sulfonate, epoxide, lactone, thiol

5. **Related compounds** — PubChem 2D similarity search, estimated Tanimoto from rank position

**Output:** `ResolvedCompound` — name, canonical SMILES, InChI/Key, PubChem CID, synonyms, CAS numbers, molecular formula/weight, Morgan FP, MACCS keys, functional groups, related compounds, original input metadata.

### Step 1b — Query Expansion

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step1b_expand.py`
**Entry point:** `async def expand_search_queries(compound: ResolvedCompound) -> ExpandedSearchQueries`

Uses a search-agent pattern: Claude Haiku is given a `web_search` tool (Tavily) and autonomously decides what to search for — CPC codes, assignee names, production methods — then generates structured output grounded in real search results. The explicitly ungrounded screening profile can use constrained model-only expansion when Tavily is not configured and records `model_without_live_grounding` provenance. Counsel, required-record, and search-loop execution require grounding; missing or failed Tavily then propagates instead of silently weakening the evidence boundary.

| Setting | Default | Description |
|---------|---------|-------------|
| `resolve_similarity_threshold` | 0.7 | PubChem similarity cutoff |
| `resolve_max_related_compounds` | 20 | Max related compounds returned |
| `resolve_max_synonyms` | 100 | Max synonyms stored |
| `resolve_tanimoto_step` | 0.02 | Score decay per rank position |

---

## 5. Step 2 — Multi-Source Patent Search and Ranking Funnel

### Step 2 — Multi-Source Patent Search

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step2_search.py`
**Entry point:** `async def search_patents(compound: ResolvedCompound, ...) -> tuple[list[PatentHit], SourceHealth, list[SearchFunnelEntry]]`

Builds a capability- and configuration-dependent search plan, runs its selected
sources concurrently, merges and deduplicates results, then enriches the bounded
set with legal status, family data, and patent-term calculations.

**Phase 1 — Parallel multi-source search:**

| Source capability | What It Searches | Match Type |
|--------|-----------------|------------|
| PubChem SDQ | CID-linked patents, rich metadata (title, abstract, CPC, dates, compound count) | exact |
| SureChEMBL | Exact SMILES + Tanimoto similarity + substructure | exact/similarity/substructure |
| BigQuery (full-text) | Claims text by name, top N synonyms, top M CAS numbers | text |
| BigQuery (annotations) | NLP-extracted compound mentions | text |
| PatCID | Local InChIKey index (exact + prefix/connectivity layer) | exact |
| PubChem similarity / genus | Related structures or genus candidates when applicable | similarity/genus |
| Expanded BigQuery / EPO | CPC, assignee, translated-claim and expanded-query paths when configured | text |
| Jurisdiction sources | KIPRIS, PatentScope and USPTO ODP when requested and configured | source-specific |
| NCBI patent sequence | Sequence records for biologic or peptide matters | sequence |

The selected source tasks run concurrently. Disabled, not-applicable,
not-configured and failed capabilities are recorded explicitly in `SourceHealth`.

**Phase 2 — Merge and deduplicate:**
- Union by normalised patent ID
- Merge sources, confidence scores, match types
- Confidence based on source count: 1->0.30, 2->0.60, 3->0.85, 4+->0.95

**Phase 3 — Citation network traversal** (if `search_citation_traversal_enabled`):
- Seed IDs from multi-source search
- Traverse examiner citations up to configurable depth
- Add newly discovered patents

**Phase 4 — Post-search enrichment** (concurrent, best-effort):
- **Legal status** — EPO OPS INPADOC events
- **Patent family** — EPO OPS DOCDB family members
- **Patent term** — USPTO ODP for US granted patents

**Iterative search loop** (if `search_loop_enabled`):
The search loop is implemented in `pipeline/search_loop.py` (consolidated from six files). When enabled, Steps 2 and 3 run in up to `search_loop_max_iterations` iterations. Between iterations a coverage assessment identifies gaps; subsequent iterations search with refined queries and triage only newly discovered patents. The loop exits early when `search_loop_coverage_threshold` is met. The adaptive runtime may enable or continue the loop when source-health, coverage, or reviewer-critical signals require more evidence; see Section 3.

| Setting | Default | Description |
|---------|---------|-------------|
| `search_max_sdq_patents` | 50000 | Max from PubChem SDQ |
| `search_max_ranked_results` | 1000 | Configured Top N after ranking |
| `search_allowed_jurisdictions` | ["US", "WO", "EP", "JP", "KR", "CN", "IN", "CA", "AU"] | Jurisdiction targets |
| `search_tanimoto_threshold` | 0.55 | SureChEMBL similarity cutoff |
| `search_surechembl_substructure_enabled` | true | Enable substructure search |
| `search_max_synonyms_bigquery` | 25 | Synonyms sent to BigQuery |
| `search_max_cas_bigquery` | 10 | CAS numbers sent to BigQuery |
| `search_citation_traversal_enabled` | true | Enable citation network |
| `search_citation_max_depth` | 2 | Citation traversal depth |
| `search_citation_max_per_level` | 50 | Max citations per level |
| `search_max_legal_status_patents` | 200 | Patents enriched with legal status |
| `search_max_family_patents` | 50 | Patents enriched with family data |
| `search_max_patent_term_calc` | 50 | Patents with term calculation |
| `search_loop_enabled` | false | Enable iterative search loop |
| `search_loop_max_iterations` | 3 | Max search loop iterations |
| `search_loop_coverage_threshold` | 0.7 | Early-exit coverage confidence |

### Step 2b — Patent Ranking Funnel

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step2b_rank.py`
**Entry point:** `def rank_patents(sdq_results, compound, multi_source_ids, max_results, collect_audit) -> list[dict]`

Pure ranking logic (no external calls). Applies a 4-stage funnel:

```
Source results (bounded by configured acquisition caps)
    |
    | Stage 1: HARD FILTERS
    |   - Configured jurisdiction-target check
    |   - Kind code validation (A/B/E types only)
    |   - Expiry check (filing + 20yr + grace period)
    |
    v
filtered candidate set
    |
    | Stage 2: COMPOSITE SCORING (5 weighted signals)
    |   - CPC relevance (bio/chem CPC codes -> 1.0, others -> 0.0)
    |   - Compound count (fewer = more focused patent)
    |   - Recency (linear decay from priority date)
    |   - Title keyword match (compound name/synonyms/CAS in title)
    |   - Multi-source signal (found by other search sources)
    |
    v
configured BM25 pool (rank_bm25_pool_size)
    |
    | Stage 3: BM25 RE-RANKING
    |   - Query: compound name + synonyms + CAS numbers
    |   - Corpus: title + abstract + claims (first 2000 chars)
    |   - Library: bm25s with English stopwords
    |
    v
    |
    | Stage 4 (OPTIONAL): EMBEDDING RE-RANKING
    |   - SPECTER2/PaECTER embeddings (if enabled)
    |   - Cosine similarity on title + abstract
    |
    v
    |
    | FINAL BLEND
    |   - 2-way: 0.6 * composite + 0.4 * BM25
    |   - 3-way: 0.4 * composite + 0.3 * BM25 + 0.3 * embedding
    |
    v
configured final cap (search_max_ranked_results)
```

| Setting | Default | Description |
|---------|---------|-------------|
| `rank_weight_cpc` | 0.30 | CPC relevance weight |
| `rank_weight_compound_count` | 0.20 | Compound count weight |
| `rank_weight_recency` | 0.15 | Recency weight |
| `rank_weight_title` | 0.15 | Title match weight |
| `rank_weight_multi_source` | 0.20 | Multi-source signal weight |
| `rank_bm25_pool_size` | 1000 | Patents sent to BM25 stage |
| `rank_blend_composite_2way` | 0.6 | Composite weight in 2-way blend |
| `rank_blend_bm25_2way` | 0.4 | BM25 weight in 2-way blend |
| `embedding_ranking_enabled` | true | Enable configured embedding re-ranking |

### Step 2c — Family Expansion

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step2c_families.py`

Groups patents by family, fetches claims for family members via BigQuery, and selects the member with the broadest independent claims (heuristic breadth score based on claim length and functional language) for downstream analysis.

### Step 2d — Drawing Analysis

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step2d_drawings.py`

Extracts and analyses chemical structures from patent drawings using the gated OCSR pipeline. The current default segmentation backend is DECIMER; MolDet and ChemSAM are configuration-controlled alternatives, and MolDet's non-commercial licence prevents it from entering the beta/production evidence roster. Each crop is classified (molecule / reaction / Markush / non-chemical). Fixed-structure outputs from configured isolated OCSR workers are fused, cross-validated against text (formula, CAS, chemical names, abbreviations, and InChI/PubChem where available), and compared to the target with Tanimoto and bidirectional substructure checks. A governed Markush specialist result takes a separate direct CXSMILES structure path and does not enter that fixed-structure postprocessing/similarity pass. Both paths retain source-image hashes and governance provenance in `DrawingEvidenceStore`.

On a fresh run, drawing analysis occurs after Step 3 and is bounded to the post-triage relevant set; it does not decide which patents enter that set. Runtime initializes governance, OCSR runners, the configured segmenter and EPO client before taking the first `drawing_max_patents` candidates and applying the jurisdiction allowlist. The maximum is a truncation cap, not an eligibility failure. Drawing evidence can inform claim analysis, Doctrine-of-Equivalents screening, invalidity screening, and report-draft fields only when the configured live vision evidence contract passes. Otherwise `drawing_evidence_for_decisions` returns `None`, so shadow output cannot influence those consumers. Live bindings, a segmenter and source access are hard requirements for influence-capable execution; shadow/internal extraction can run without live bindings and uses each fetched page as one full-page segment if its segmenter is unavailable. Required live acquisition, segmentation, or OCSR execution errors stop when no trustworthy result or fallback exists. A successful lookup with no drawing, a valid no-crop result, and an unresolved low-confidence structure are recorded as per-item abstentions; recoverable classifier/preprocessing paths can continue through their documented fallbacks.

See [A09 — Runtime phase map](architecture/src/09-runtime-phase-map.md) for the implemented stage ordering and [A10 — Vision extraction and evidence fusion](architecture/src/10-vision-evidence-fusion.md) for the detailed image and record-level fusion boundaries.

---

## 6. Step 3 — LLM Triage

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step3_triage.py`
**Entry point:** `async def triage_patents(patents, compound) -> tuple[list[TriageResult], int, int]`

Uses Claude Haiku (fast, cheap) to classify each patent as RELEVANT, POSSIBLY_RELEVANT, or NOT_RELEVANT. Only RELEVANT and POSSIBLY_RELEVANT patents pass to the expensive downstream steps.

**Algorithm:**

1. **Batch patents** — groups of `triage_batch_size` (default 10)
2. **Format context** — compound info + patent title/abstract/claims (truncated)
3. **LLM call per batch** — Claude Haiku with prompt caching (system prompt reused)
4. **Output per patent:** relevance classification, reasoning, key claim numbers, confidence score
5. **Filter** — only RELEVANT + POSSIBLY_RELEVANT pass to Step 4

**Concurrency:** `asyncio.Semaphore(triage_concurrency)` limits parallel LLM calls. Prompt caching via `cache_system=True` reduces cost across batches.

| Setting | Default | Description |
|---------|---------|-------------|
| `triage_batch_size` | 10 | Patents per LLM call |
| `triage_concurrency` | 3 | Max parallel triage calls |
| `triage_max_abstract_chars` | 5000 | Abstract truncation |
| `triage_max_claims_chars` | 30000 | Claims truncation |

---

## 7. Step 4 — Claim Analysis

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step4_analyze.py`
**Entry point:** `async def analyze_patents_with_context(patents, compound, triage_results, drawing_evidence) -> tuple[list[PatentAnalysis], list[AnalysisFailure], list[ReasoningTrace], dict]`

The core of the FTO analysis. For each triaged patent, it runs the unified `world_class_adaptive` analysis path. There are no user-selectable lite/advanced or standard/deep methods.

**Algorithm:**

1. **Claims enrichment** — batch-fetch missing claims text from BigQuery
2. **Prosecution context** — fetch and parse USPTO file wrappers for each patent
3. **For each patent** (concurrent, capped at `max_analysis_patents`):
   - Run the single-pass stage with extended thinking (`analysis_thinking_budget_tokens`), enriched claim/prosecution/spec context, optional drawing evidence, and deterministic risk checks.
   - Run the evaluator pass (Claude Haiku) for risk-claim consistency, element status consistency, missing analyses, confidence calibration, and poor-quality detection.
   - Escalate automatically into the agentic stage when risk, density, uncertainty, evaluator quality, source health, drawing evidence, Markush ambiguity, or reviewer-critical signals require it.
   - Run the multi-perspective pass when enabled and the adaptive metadata indicates high risk, uncertainty, or escalation.

   The unified path produces `PatentAnalysis` with:
   - Per independent claim: preamble, transitional phrase, element decomposition
   - Per element: status (MET / NOT_MET / PARTIALLY_MET / UNCLEAR), reasoning, evidence, confidence
   - Overall risk level: HIGH / MEDIUM / LOW / CLEAR
   - Design-around suggestions

4. **Deterministic risk computation** (when `deterministic_risk_computation=True`):
   - Risk level is computed from element statuses, overriding the LLM's stated risk if they disagree

### Risk Level Determination

| Risk | Criteria |
|------|----------|
| HIGH | >=1 independent claim with ALL elements MET |
| MEDIUM | Most elements MET with some UNCLEAR |
| LOW | No claim fully met |
| CLEAR | No claims cover the target compound |

### Step 4b — Portfolio Critic

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step4b_critic.py`

After the per-patent analysis batch, an adaptive portfolio-level critic review runs when `critic_enabled=True`. Compact review is used for simple, clear portfolios; agentic critic behavior is used for dense, high-risk, uncertain, escalated, or reviewer-critical portfolios. It checks cross-portfolio consistency: conflicting risk ratings for related claims, patterns suggesting under- or over-claiming, and coherence across the patent landscape. It produces a `CriticReport` with findings and a quality score. When `critic_reanalysis_enabled=True`, the critic may flag up to `critic_reanalysis_max_patents` patents for re-analysis.

| Setting | Default | Description |
|---------|---------|-------------|
| `max_analysis_patents` | 100 | Max patents analysed (cost control) |
| `analysis_concurrency` | 5 | Max parallel analysis calls |
| `analysis_thinking_budget_tokens` | 32000 | Extended thinking token budget |
| `analysis_max_tokens` | 64000 | Max output tokens per analysis call |
| `critic_enabled` | true | Enable portfolio critic review |
| `critic_max_tokens` | 16384 | Max output tokens for critic |
| `critic_reanalysis_enabled` | false | Allow critic to trigger re-analysis |
| `critic_reanalysis_max_patents` | 3 | Max patents re-analysed by critic |
| `agentic_max_agent_rounds` | 5 | Max research rounds for agentic escalation |
| `deterministic_risk_computation` | true | Compute risk from element statuses |

---

## 8. Step 5 — Doctrine of Equivalents

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step5_doe.py`
**Entry point:** `async def assess_equivalents(analyses, compound, drawing_evidence, prosecution_cache) -> tuple[list[DoEAssessment], int, int]`

For elements that were NOT_MET or PARTIALLY_MET in HIGH/MEDIUM risk patents, checks whether the Doctrine of Equivalents (DoE) could expand infringement coverage. Two-phase process: estoppel check, then Function-Way-Result (FWR) test.

**Algorithm:**

1. **Candidate identification** — find NOT_MET/PARTIALLY_MET elements in HIGH/MEDIUM risk patents
2. **Sort by risk** — HIGH first, then MEDIUM
3. **Truncate** — cap at `max_doe_candidates`
4. **For each candidate:**

   **Phase A — Prosecution History Estoppel:**
   - Fetch USPTO file wrapper via `fetch_prosecution_history()`
   - Identify narrowing amendments made in response to rejections
   - If estoppel applies -> DoE is barred for surrendered scope

   **Phase B — Function-Way-Result Test** (if no estoppel):
   - LLM assesses three prongs: Function, Way, Result
   - All three must be TRUE for equivalence
   - Chemical context: bioisostere, homolog, stereoisomer, salt form, polymorph, prodrug, metabolic equivalent
   - Known interchangeability boosts confidence

5. **Confidence bands:** HIGH (>=0.65), MODERATE (>=0.40), LOW (<0.40)

| Setting | Default | Description |
|---------|---------|-------------|
| `max_doe_candidates` | 15 | Max elements assessed for DoE |
| `doe_concurrency` | 2 | Max parallel FWR calls |

---

## 9. Step 6 — Invalidity Screening

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step6_invalid.py`
**Entry point:** `async def assess_invalidity(blocking_patents, compound, patent_hits, drawing_evidence) -> tuple[list[InvalidityAssessment], int, int]`

For HIGH and MEDIUM risk patents, screens for potential invalidity arguments under 35 U.S.C. §102 (anticipation), §103 (obviousness), and §112 (enablement/written description). Combines deterministic PTAB data with scholarly prior art search and LLM-assisted claim chart construction.

**Per blocking patent, 4 tasks run in parallel:**

| Task | Source | Output |
|------|--------|--------|
| PTAB check | USPTO PTAB API | `PTABResult` — proceedings, challenged/cancelled claims |
| Scholarly prior art | Semantic Scholar + OpenAlex | `list[PriorArtReference]` — papers published before priority date |
| Examiner citations | BigQuery (batch) | Dict of examiner + applicant cited references |
| LLM invalidity screening | Claude Sonnet | `InvalidityLLMResponse` — arguments, claim charts, Graham factors |

**LLM invalidity screening produces:**
- Invalidity arguments (anticipation, obviousness, written description)
- Claim charts — element-by-element mapping to prior art disclosures
- Graham factors — scope of prior art, differences, level of ordinary skill, secondary considerations
- Enablement screening — genus claim flags, Amgen v. Sanofi analysis, undue experimentation indicators

**Confidence bands:** HIGH (>=0.70), MODERATE (>=0.45), LOW (<0.45)

| Setting | Default | Description |
|---------|---------|-------------|
| `scholarly_max_synonyms` | 5 | Synonyms used in scholarly search |
| `scholarly_early_exit_threshold` | 20 | Stop secondary queries if enough results |
Lens client wrappers exist for offline experiments, but the active runtime plan keeps Lens out of Step 2 and Step 6. Do not require or document `LENS_API_KEY` for the hosted reference until that gate is intentionally reopened.

---

## 10. Step 7 — Deterministic Verification

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step7_verify.py`
**Entry point:** `def verify_analysis(analyses, doe_assessments, invalidity_assessments, search_results) -> VerificationResult`

Runs 10 deterministic checks (no LLM) to validate internal consistency across all pipeline outputs. This is the safety net before report generation.

**The 10 Checks:**

| # | Check | What It Validates |
|---|-------|-------------------|
| 1 | Citation grounding | Every analysed patent ID exists in search results |
| 2 | Chemical entity validation | SMILES in design-around suggestions parse in RDKit |
| 3 | Risk consistency | HIGH risk requires >=1 MET/PARTIALLY_MET claim |
| 4 | Date consistency | Expiry years fall in 1990-2050 range |
| 5 | Legal status consistency | HIGH risk patents have ACTIVE/UNKNOWN status (not EXPIRED/LAPSED/REVOKED) |
| 6 | DoE consistency | All DoE assessments reference valid patent/claim combos from Step 4 |
| 7 | Invalidity consistency | Invalidity assessments reference analysed patents with valid strength values |
| 8 | Claims grounded | Analysed patents have claims text in search results |
| 9 | Claim chart consistency | Chart references point to valid prior art IDs |
| 10 | Prosecution history consistency | `estoppel_applies` matches narrowing amendment counts |

All checks run — no early exit. Issues are aggregated in `VerificationResult`.

---

## 11. Step 8 — Report Generation

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step8_report.py`
**Entry point:** `async def generate_report(...) -> FTOReport`

`step8_report.py` routes unconditionally to the unified five-stage agentic report pipeline. Legacy v1/v2 report dispatch has been removed from active runtime. Reports stamp `execution_profile` and `report_pipeline` as `world_class_adaptive`; legacy report metadata fields such as `pipeline_mode` and `analysis_depth` are not emitted.

### Step 8 — Unified Five-Stage Agentic Pipeline

**File:** `praviar_pipeline/src/praviar_pipeline/pipeline/step8_unified_report.py`

This is the only report generator reachable from the active runtime path.

Generates the report in five stages:

1. **DATA INDEX** — builds a queryable data store from all pipeline artifacts
2. **SECTION GENERATION** — six sections generated concurrently (up to `report_section_concurrency`), each with tool access to query pipeline data on demand:
   - S1 Executive Summary
   - S2 Key Patent Analysis
   - S3 Damages and Injunction Risk
   - S4 Invalidity, DoE, and PTAB
   - S5 Recommendations and Monitoring
   - S6 Data Quality and Limitations
3. **DETERMINISTIC VERIFY** — `run_deterministic_validators` checks all generated sections
4. **LLM VERIFY** — verification agent with extended thinking (`report_verification_thinking_budget`) checks alignment with the indexed pipeline artefacts when enabled via `report_verification_enabled`; it is not independent source or legal validation
5. **ASSEMBLE** — assembles all sections into the final `FTOReport`

Key output fields include `bibliography` (auto-generated with Google Patents / DOI / PTAB links, when `report_bibliography_enabled=True`), `factual_accuracy_rate`, `verification_summary`, `execution_profile`, and `report_pipeline`. `factual_accuracy_rate` is the pipeline's internal artefact-alignment score; its name must not be interpreted as measured legal accuracy or source truth.

Sections that fail validation are retried up to `report_max_section_retries` times.

| Setting | Default | Description |
|---------|---------|-------------|
| `report_section_concurrency` | 6 | Max concurrent section generation calls |
| `report_verification_enabled` | true | Enable LLM fact verification stage |
| `report_bibliography_enabled` | true | Enable auto-generated reference appendix |
| `report_verification_thinking_budget` | 32768 | Extended thinking budget for verification agent |
| `report_max_section_retries` | 2 | Max retries per section after validation failure |

### Output Formats

| Format | Implementation |
|--------|---------------|
| JSON | Native Pydantic serialisation |
| Markdown | `render_markdown(report)` — deterministic, no LLM |
| PDF | `render_pdf(report)` — Typst template + Matplotlib charts |

---

## 12. Runtime Orchestration Layer

**Directory:** `praviar_pipeline/src/praviar_pipeline/pipeline/runtime/`

The runtime orchestration layer wraps the 8 pipeline steps in checkpoint-aware, cancellation-aware orchestration. It is consumed by the CLI (`cli.py`, `cli_runner.py`) and by the API worker.

**Key files:**

| File | Responsibility |
|------|---------------|
| `run_execution.py` | Top-level flow: `execute_resolution_to_search_flow`, `execute_analysis_to_verification_flow` |
| `pipeline_steps.py` | Per-step runners: `run_resolution_step`, `run_query_expansion_step`, `run_search_step`, `run_triage_step`, `run_analysis_step` |
| `post_analysis.py` | Post-analysis runners: `run_critic_review`, `run_doe_assessment`, `run_invalidity_assessment`, `run_verification_step` |
| `flow_bootstrap.py` | `bootstrap_run_context` — creates the mutable run context, restores from checkpoint if `--resume` is supplied, seeds the RNG, installs cost/provenance/cache context, and enables the search loop when initial adaptive-escalation reasons require it |
| `flow_finalize.py` | `finalize_report_output` — tears down the cost tracker, stamps the manifest |
| `checkpoints.py` | `RuntimeCheckpointState`, `restore_runtime_state` |
| `search_enrichment.py` | `run_post_search_enrichment`, `run_claims_enrichment` |
| `live_collectors.py` | `execute_live_evidence_collectors` — deterministic authoritative collectors for gaps identified at runtime |
| `audit.py` | `build_triage_audit`, `build_analysis_audit` |
| `run_lifecycle.py` | Cancellation helpers, step timing, deadline enforcement |
| `reanalysis.py` | Critic-triggered re-analysis flow |

**Checkpoint behaviour:**
`checkpoint_enabled` (default `True`) saves a `PipelineCheckpoint` after each completed step. A run interrupted mid-pipeline can be resumed from the last checkpoint using `--resume <checkpoint_dir>`. Current checkpoints carry `execution_profile="world_class_adaptive"` and `analysis_escalation_reasons`. Legacy mode/depth checkpoint fields are rejected; there is no compatibility shim for `pipeline_mode` or `claim_analysis_depth`.

**Human-in-the-loop (HITL):**
When `hitl_enabled=True`, configured identity, analysis, and report-review checkpoints are blocking: approval continues, rejection stops, and timeout/no persisted decision fails closed to `review_required`. The configured triage-review checkpoint is an emitted non-blocking event and the pipeline continues immediately. Report finalization first builds the initial non-vision matter evidence index, then binds prompt hashes and the exact `ClaimSourceSpanMap` and rejects unsupported customer-visible claims. `build_report_review_checkpoint_context` validates verified-claim source-span attestations and emits a bounded `report-review/v1` decision brief: IDs, upstream risk, patent/failure counts, an executive-summary excerpt of at most 1,200 characters plus truncation flag, aggregate claim-ledger counts and attestation-key IDs, prompt-hash count, digest-bound checkpoint ID, and a SHA-256 receipt. The receipt covers the bounded decision brief, the complete private claim/source map, and complete sorted prompt-hash map; the context intentionally omits the full `FTOReport`, private map, source excerpts, evidence HMAC receipts, and individual prompt hashes. When configured, the web gate displays the risk, excerpt, ledger metrics and digest, blocks approval for malformed/unsupported context, requires explicit checkbox attestation, and persists the full digest in the approval note. This is a bounded decision-brief checkpoint, not a review of the full final report or the downstream clearance outcome. It occurs before `attach_report_runtime_metadata`, the clearance-time index rebuild, coverage and decision gates, matter-graph attachment, manifest construction, and final output.

---

## 13. Decisioning and Evidence Graph Layer

**Directory:** `praviar_pipeline/src/praviar_pipeline/pipeline/runtime/` (decisioning_* and evidence_* files, matter_graph_*, matter_store.py)

Report finalization builds an initial non-vision `MatterEvidenceIndex` into the draft before the blocking report-review checkpoint. After approval (or when review is not configured), the runtime builds the deterministic clearance layer that answers the top-line question: is this compound clear? `attach_report_runtime_metadata` invokes `build_clearance_outputs` only after that checkpoint; the builder reconstructs the index from the completed report and patent records, computes coverage and gates, and assembles clearance metadata. This layer is not LLM-driven.

### Signal Extraction

**File:** `decisioning_signals.py`

Extracts `PatentDetailSignals` from each patent: prosecution availability, amendment counts, narrowing-signal flag, terminal disclaimer, PTAB challenge status, pending family signals, and EPO register event counts. These signals feed the decisioning metrics.

### Evidence Graph

**Files:** `evidence_graph.py`, `evidence_runtime.py`, `evidence_collectors.py`, `evidence_artifacts.py`, `evidence_claims.py`, `evidence_policy.py`

Builds an `EvidenceArtifact` per patent from non-vision record data such as claims text, prosecution dossier, family context, legal events, source health, and collector receipts. Produces `EvidenceAdapterResult` records that describe which components were obtained from which authoritative sources. The live collectors (`live_collectors.py`) fill gaps identified by comparing required record components against what was actually obtained. Drawing evidence can influence analyses and report-draft fields when governed, but neither the pre-review nor clearance-time `build_matter_evidence_index` call, nor the matter-graph builders, accepts the drawing store, drawing structures, image hashes, or drawing scores as direct inputs.

### Matter Graph

**Files:** `matter_graph_state.py`, `matter_graph_snapshot.py`, `matter_store.py`

Constructs a `MatterGraph` of typed nodes (`MatterNode`) and edges (`MatterEdge`) representing the relationships between the target compound, patents, claims, prosecution events, and prior art. The graph is summarised into `MatterGraphSummary` for consumption by the decisioning layer.

### Decisioning

**Files:** `decisioning.py`, `decisioning_coverage.py`, `decisioning_metrics.py`, `decisioning_outputs.py`, `decisioning_references.py`

`build_clearance_outputs` assembles the final `ClearanceDecision`:

1. Builds `DecisionCoverageContext` — ratios of patents with claims, family context, prosecution dossier, and authoritative records.
2. Scores evidence quality across five dimensions: source OK ratio, claims coverage, family coverage, US prosecution coverage, EP register coverage.
3. Applies jurisdiction gates — `JurisdictionDecision` per jurisdiction (US, EP, WO, etc.) based on `jurisdiction_policy`.
4. Applies clearance gates — checks required record components, source authority policy, and cohort status.
5. Determines the actual `ClearanceOutcome` enum (`CLEAR`, `UNCLEAR`, or `BLOCKED`) and `ClearanceDecisionAudit`. `CLEAR` requires strict evidence-quality, sufficiency, warning, and claim-program gates; blocking patents without an authoritative-record contradiction yield `BLOCKED`; all other states yield `UNCLEAR`.
6. Builds `ClaimProgramSummary` — claim-level decisions aggregated across all analysed patents.
7. Builds `RunObservability` — timing, token counts, cost, step results for operational monitoring.

`determine_clearance_decision` and `determine_decision_confidence` in `decisioning_outputs.py` are the entry points for the final verdict and its confidence level.

---

## 14. Data Model Reference

All models use `ConfigDict(extra="forbid")` for strict validation. Located in `praviar_pipeline/src/praviar_pipeline/models/`.

### Model Dependency Graph

```
ResolvedCompound
  +-- RelatedCompound[]

ExpandedSearchQueries

PatentHit
  +-- LegalEvent[]
  +-- PatentFamily
  |     +-- PatentFamilyMember[]
  +-- PatentTermInfo

TriageResult
  (standalone, references patent_id)

PatentAnalysis
  +-- ClaimAnalysis[]
  |     +-- ClaimElement[]
  +-- DesignAroundSuggestion[]

AnalysisEvaluation
  +-- EvaluationIssue[]

CriticReport
  +-- CriticFinding[]

DoEAssessment
  +-- EstoppelResult
  +-- FWRAssessment
        +-- ChemicalEquivalenceContext

ProsecutionHistory
  +-- RejectionRecord[]
  +-- ClaimAmendment[]

InvalidityAssessment
  +-- PTABResult
  |     +-- PTABProceeding[]
  +-- PriorArtReference[]
  +-- ClaimChart[]
  |     +-- ClaimChartEntry[]
  +-- GrahamFactors
  +-- EnablementScreening

VerificationResult
  +-- VerificationCheck[]

FTOReport                          <-- top-level output
  +-- ResolvedCompound
  +-- RiskSummary
  +-- PatentAnalysis[]
  +-- DoEAssessment[]
  +-- InvalidityAssessment[]
  +-- VerificationResult
  +-- SourceHealth
  |     +-- SourceHealthEntry[]
  +-- PipelineAuditTrail
  |     +-- SearchFunnelEntry[]
  |     +-- TriageAuditEntry[]
  |     +-- AnalysisAuditEntry[]
  |     +-- StepTiming[]
  +-- CriticReport (optional)
  +-- DrawingEvidenceStore (optional)

MatterGraph                        <-- post-report decisioning
  +-- MatterNode[]
  +-- MatterEdge[]

ClearanceDecision
  +-- JurisdictionDecision[]
  +-- ClaimProgramSummary
  +-- ClearanceDecisionAudit
  +-- RunObservability
```

### Key Enums

| Enum | Values | Used In |
|------|--------|---------|
| `RiskLevel` | HIGH, MEDIUM, LOW, CLEAR | PatentAnalysis, RiskSummary |
| `ElementStatus` | MET, NOT_MET, PARTIALLY_MET, UNCLEAR | ClaimElement, ClaimAnalysis |
| `Relevance` | RELEVANT, POSSIBLY_RELEVANT, NOT_RELEVANT | TriageResult |
| `PatentSource` | BIGQUERY, SURECHEMBL, PUBCHEM, PATCID, INPADOC | PatentHit |
| `LegalStatus` | ACTIVE, EXPIRED, LAPSED, REVOKED, PENDING, UNKNOWN | PatentHit enrichment |
| `SourceStatus` | OK, FAILED, SKIPPED | SourceHealthEntry |
| `ClearanceOutcome` | CLEAR (`clear`), UNCLEAR (`unclear`), BLOCKED (`blocked`) | ClearanceDecision |
| `MatterNodeType` | COMPOUND, PATENT, CLAIM, APPLICATION, PRIOR_ART, ... | MatterGraph |

---

## 15. External Clients

All clients inherit from `AsyncClientMixin` (async context manager). Located in `praviar_pipeline/src/praviar_pipeline/clients/`.

| Client | External Service | Auth | Rate Limit | Key Methods |
|--------|-----------------|------|------------|-------------|
| `PubChemClient` | PubChem PUG REST + SDQ | None (public) | Operator-configured local cap | `resolve_by_name`, `sdq_search_patents`, `similarity_search` |
| `BigQueryClient` | Google BigQuery (patents-public-data) | Service account | Bytes billed cap | `search_patents_by_compound`, `get_patent_claims_batch`, `get_examiner_citations_batch` |
| `SureChEMBLClient` | SureChEMBL REST | None | Operator-configured local cap | `search_by_smiles`, `similarity_search`, `substructure_search` |
| `PatCIDClient` | Local SQLite index | None | None | `lookup_by_inchikey`, `lookup_by_inchikey_prefix` |
| `USPTOODPClient` | USPTO Open Data Portal v1 | API key | Operator-configured local cap | `get_file_wrapper_documents`, `get_application_data`, `get_continuity_data` |
| `PTABClient` | USPTO PTAB API v3 | Bearer token | — | `get_proceedings`, `get_final_written_decisions` |
| `EPOOPSClient` | EPO OPS v3.2 | OAuth2 (key/secret) | Operator-configured local cap | `get_legal_status`, `get_family` |
| `SemanticScholarClient` | Semantic Scholar Graph API | Optional API key | Conservative local cap | `search_papers`, `get_paper` |
| `OpenAlexClient` | OpenAlex API | API key required when used | Operator-configured local cap | `search_works` |
| `LensClient` | Lens.org API | Bearer token | Operator-configured local cap | Dormant/offline experiments only; not scheduled by the active runtime |
| `TavilyClient` | Tavily Search API | API key | SDK-managed | `search` (used by query expansion agent) |
| `ClaudeClient` | Anthropic Claude API | API key | SDK-managed | `complete`, `complete_with_thinking`, `complete_text` |

### Retry Strategy (all HTTP clients)
- **tenacity**: 3 attempts, exponential backoff (1s initial, 10-20s max)
- **Authentication errors**: never retried (fail immediately)
- **404 responses**: return empty dict/list (resource not found is not an error)
- **Semantic Scholar special case**: 2-layer retry — inner (3 attempts for 5xx) + outer (8 attempts for 429 with `Retry-After` header)

---

## 16. Configuration Reference

All settings are in `praviar_pipeline/src/praviar_pipeline/config.py` via `pydantic-settings`, loaded from `.env`. The `Settings` class composes several mixin classes (`PipelineExecutionSettingsMixin`, `QualityAndDisplaySettingsMixin`, `SearchSourceSettingsMixin`, and others) defined across `config_*_sections.py` files.

### API Keys

| Setting | Env Var | Required |
|---------|---------|----------|
| `anthropic_api_key` | `ANTHROPIC_API_KEY` | Yes (raises `ConfigurationError`) |
| `google_application_credentials` | `GOOGLE_APPLICATION_CREDENTIALS` | For BigQuery |
| `bigquery_project_id` | `BIGQUERY_PROJECT_ID` | For BigQuery |
| `uspto_odp_api_key` | `USPTO_ODP_API_KEY` | For USPTO/PTAB |
| `ops_consumer_key` | `OPS_CONSUMER_KEY` | For EPO OPS |
| `ops_consumer_secret` | `OPS_CONSUMER_SECRET` | For EPO OPS |
| `semantic_scholar_api_key` | `SEMANTIC_SCHOLAR_API_KEY` | Optional (faster rate) |
| `openalex_api_key` | `OPENALEX_API_KEY` | Required when OpenAlex is used (fails before request when missing) |
| `tavily_api_key` | `TAVILY_API_KEY` | Optional (query expansion grounding) |

### LLM Models

| Setting | Default | Used For |
|---------|---------|----------|
| `claude_triage_model` | claude-haiku-4-5-20251001 | Triage (Step 3), evaluator (Step 4), query expansion (Step 1b) |
| `claude_analysis_model` | claude-sonnet-4-6 | DoE FWR (Step 5), invalidity (Step 6), report narratives (Step 8), and adaptive portfolio review |
| `claude_deep_model` | claude-sonnet-4-6 | Step 4 single-pass analysis and agentic escalation model role |

### Execution Profile

| Setting | Default | Description |
|---------|---------|-------------|
| `search_loop_enabled` | false | Enable iterative search loop. Runtime signals may also enable it during adaptive execution. |
| `agentic_max_agent_rounds` | 5 | Max research rounds for agentic escalation. |
| `agentic_observation_masking` | true | Mask old tool outputs during agentic escalation. |
| `agentic_scratchpad_enabled` | true | Maintain structured scratchpad state across agent rounds. |

### Pipeline Concurrency

| Setting | Default | Controls |
|---------|---------|----------|
| `triage_concurrency` | 3 | Parallel Haiku calls in Step 3 |
| `analysis_concurrency` | 5 | Parallel patent-analysis calls in Step 4 and invalidity calls in Step 6 |
| `doe_concurrency` | 2 | Parallel FWR calls in Step 5 |
| `narrative_concurrency` | 2 | Parallel per-patent narrative calls in Step 8 |
| `report_section_concurrency` | 6 | Parallel section generation calls in Step 8 |

### Singleton Access

```python
from praviar_pipeline.config import get_settings

settings = get_settings()  # Cached via @lru_cache
settings.anthropic_api_key          # "sk-ant-..."
settings.claude_deep_model          # "claude-sonnet-4-6"
settings.search_loop_enabled        # False
settings.rate_limits.pubchem_rps    # 5.0
```

---

## 17. Prompt Templates

Located in `praviar_pipeline/src/praviar_pipeline/prompts/`. Loaded at runtime via `ClaudeClient.load_prompt()`.

| File | Step | Model | Purpose |
|------|------|-------|---------|
| `query_expansion_system.txt` | 1b | Haiku | LLM query expansion with optional Tavily grounding |
| `triage_system.txt` | 3 | Haiku | Classify patents as RELEVANT/POSSIBLY_RELEVANT/NOT_RELEVANT |
| `claim_analysis_system.txt` | 4 | Opus/Sonnet | Element-by-element claim analysis with risk determination |
| `multi_perspective_section.txt` | 4 | Opus/Sonnet | Multi-perspective appendix for adaptive review |
| `evaluator_system.txt` | 4 | Haiku | QA pass on claim analysis (risk-claim mismatch, calibration) |
| `doe_fwr_system.txt` | 5 | Sonnet | Function-Way-Result test (basic) |
| `doe_fwr_screening_system.txt` | 5 | Sonnet | FWR with chemical equivalence context + estoppel |
| `invalidity_system.txt` | 6 | Sonnet | Invalidity assessment (basic) |
| `invalidity_screening_system.txt` | 6 | Sonnet | Full invalidity with claim charts, Graham factors, enablement |
| `report_s1_executive.txt` | 8 | Sonnet | S1 Executive Summary (agentic, with data tool access) |
| `report_s2_key_patents.txt` | 8 | Sonnet | S2 Key Patent Analysis |
| `report_s3_damages_injunction.txt` | 8 | Sonnet | S3 Damages and Injunction Risk |
| `report_s4_invalidity.txt` | 8 | Sonnet | S4 Invalidity, DoE, and PTAB |
| `report_s5_recommendations.txt` | 8 | Sonnet | S5 Recommendations and Monitoring |
| `report_s6_data_quality.txt` | 8 | Sonnet | S6 Data Quality and Limitations |

---

## 18. API Layer

The pipeline is exposed via FastAPI at `api/src/api/`. Key routes:

### Pipeline Execution

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/analyses` | Start the pipeline (Cloud Tasks in the hosted reference profile; explicit local dispatcher in development) |
| `GET` | `/analyses/{id}/stream` | SSE endpoint for real-time pipeline progress (Redis PubSub) |

### Results

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/analyses` | List analyses (org-scoped, paginated) |
| `GET` | `/analyses/{id}` | Get single analysis |
| `GET` | `/reports/{id}` | Full FTO report (ATTORNEY+ only) |
| `GET` | `/reports/{id}/summary` | Executive summary (all roles) |
| `POST` | `/reports/{id}/export` | Export as PDF/DOCX/XLSX/JSON |
| `GET` | `/patents` | Browse patents across analyses |
| `GET` | `/patents/{patent_id}` | Deep-dive with DoE + invalidity data |

### Collaboration

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/comments` | Comment on analysis (threaded) |
| `POST` | `/feedback` | Attorney corrections on report |
| `POST` | `/reports/{id}/share` | Create and deliver a recipient-bound external report grant |
| `GET` | `/reports/{id}/share` | List recipient-bound grants without exposing their secret tokens |

### Configuration

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/configs/presets` | List org configuration presets |
| `POST` | `/configs/presets` | Create preset (ATTORNEY only) |
| `PUT` | `/configs/defaults` | Set org-wide defaults (ATTORNEY only) |

### Auth
- Clerk webhooks for user/org sync (`POST /webhooks/clerk`)
- Role-based access: ADMIN, ATTORNEY, SCIENTIST, CLIENT
- Org-level multi-tenancy on all data

---

## 19. Error Handling Philosophy

Praviar Pipeline follows a **fail-fast, no-fallbacks** development philosophy:

1. **No silent exception swallowing** — every `except` block either raises or logs at `error` level with `exc_info=True`
2. **No fallback data** — if a data source fails, the error propagates (no returning empty results and pretending success)
3. **No hardcoded values** — all thresholds, weights, limits, and API keys are in `Settings`
4. **`asyncio.gather(return_exceptions=True)`** — exceptions are captured in results, then logged individually at `error` level
5. **LLM output validation** — Pydantic validators coerce LLM outputs (case normalisation, synonym mapping) but reject structurally invalid data
6. **Deterministic verification** — Step 7 catches inconsistencies that LLMs might introduce (hallucinated patent IDs, risk-claim mismatches)
7. **Report validation** — executive summary is checked for hallucinated patents, missing risk levels, and word count bounds before inclusion

This ensures that during development, every issue is immediately visible rather than hidden behind silent fallbacks.
