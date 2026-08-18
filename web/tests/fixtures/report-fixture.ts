/**
 * Legacy development and component-test fixture.
 *
 * Every organization, person, publication identifier, legal record, citation,
 * and conclusion below is synthetic. Real chemistry terms are neutral UI test
 * inputs only. This is not the canonical showcase and is not release evidence.
 */

import type {
  FTOReport,
  ResolvedCompound,
  PatentAnalysis,
  ClaimElement,
  DoEAssessment,
  InvalidityAssessment,
  VerificationResult,
  SourceHealth,
  PipelineAuditTrail,
  StepTokenUsage,
  RiskSummary,
  AnalysisFailure,
  DataLimitation,
  ActionItem,
} from "@praviar/shared-types";

// ── Resolved compound ──────────────────────────────────────────────────

const SUCCINIC_ACID: ResolvedCompound = {
  name: "succinic acid",
  canonical_smiles: "OC(=O)CCC(O)=O",
  inchi: "InChI=1S/C4H6O4/c5-3(6)1-2-4(7)8/h1-2H2,(H,5,6)(H,7,8)",
  inchi_key: "KDYFGRWQOYBRFD-UHFFFAOYSA-N",
  pubchem_cid: 1110,
  synonyms: [
    "succinic acid",
    "butanedioic acid",
    "1,2-ethanedicarboxylic acid",
    "amber acid",
    "spirit of amber",
  ],
  cas_numbers: ["110-15-6"],
  molecular_formula: "C4H6O4",
  molecular_weight: 118.09,
  morgan_fp:
    "00000000000000000000000000001000000000000010000000000000000000000000000000000000000100001000000001001000000000100000000000000000",
  maccs_keys:
    "00000000000000000000000000000000000010001000000000000000100000000001010000010000000000010000100100001001000100001100010011000010",
  functional_groups: ["carboxylic acid", "dicarboxylic acid"],
  related_compounds: [
    {
      cid: 196,
      name: "citric acid",
      canonical_smiles: "OC(=O)CC(O)(CC(O)=O)C(O)=O",
      tanimoto_similarity: 0.61,
    },
    {
      cid: 5862,
      name: "glutaric acid",
      canonical_smiles: "OC(=O)CCCC(O)=O",
      tanimoto_similarity: 0.85,
    },
    {
      cid: 8628,
      name: "malic acid",
      canonical_smiles: "OC(CC(O)=O)C(O)=O",
      tanimoto_similarity: 0.72,
    },
  ],
  original_input: "succinic acid",
  input_type: "name",
};

// ── Risk summary ───────────────────────────────────────────────────────

const RISK_SUMMARY: RiskSummary = {
  overall_risk: "high",
  blocking_patents_count: 3,
  total_patents_analyzed: 5,
  key_risks: [
    "US0000000001A1 (Fictional Meridian) claims a process for producing C4 dicarboxylic acids including succinic acid via engineered E. coli fermentation; the claim scope is broad enough to read on standard bio-based production routes.",
    "US0000000002A1 (Fictional Atlas) covers crystallization and purification of bio-succinic acid from fermentation broth at yields above 85%, which overlaps with common downstream processing protocols.",
    "US0000000003A1 (Fictional Nova) discloses engineered Aspergillus niger strains secreting fumarase variants that convert fumaric acid to succinic acid at titers exceeding 40 g/L, creating medium risk for enzymatic conversion approaches.",
  ],
  executive_summary:
    "This freedom-to-operate analysis evaluated succinic acid (CID 1110, butanedioic acid) against 2,417 patents discovered across PubChem, SureChEMBL, Google Patents (BigQuery), and PatCID. After automated hard-filtering, composite scoring, and BM25 re-ranking, 47 patents passed triage for detailed claim-level analysis.\n\nOf the five patents subjected to element-by-element claim analysis, two present high infringement risk. US0000000001A1 (assigned to Fictional Meridian) contains broad independent claims covering microbial fermentation of C4 dicarboxylic acids using recombinant prokaryotic hosts, and three of four claim elements are met by a standard bio-succinic production process. US0000000002A1 (assigned to Fictional Atlas) claims a purification method for crystallizing bio-based succinic acid from aqueous fermentation broth, with both independent claim elements satisfied. Design-around opportunities exist primarily through alternative downstream processing (e.g., reactive extraction with tri-n-octylamine rather than crystallization) or through use of eukaryotic hosts not covered by the Fictional Meridian claims.\n\nInvalidity analysis identified potentially strong prior art against both high-risk patents. The Fictional Atlas crystallization patent faces an anticipation argument based on a 2008 Fictional Reference Gamma publication describing substantially identical crystallization conditions. The Fictional Meridian fermentation patent is vulnerable to an obviousness challenge under Graham v. John Deere given well-known metabolic engineering of E. coli for succinate production published by Fictional Reference Beta (2002). A PTAB inter partes review (IPR0000-00001) was filed against the Fictional Meridian patent but was denied institution. Overall, we recommend engaging patent counsel to evaluate design-around strategies and monitor the status of these patents before proceeding with commercialization.",
  summary_validation_issues: [
    "Two high-risk patents share overlapping claim scope on the fermentation element. The risk assessment may double-count this infringement vector.",
  ],
};

// ── Patent analyses ────────────────────────────────────────────────────

const CLAIM_ELEMENTS_MERIDIAN: ClaimElement[] = [
  {
    element_number: 1,
    element_text:
      "A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism",
    status: "met",
    reasoning:
      "The production process under evaluation uses a recombinant E. coli strain (a prokaryotic microorganism) to produce succinic acid, which is a C4 dicarboxylic acid. This element is clearly met.",
    confidence: 0.95,
    evidence:
      "Succinic acid (butanedioic acid, C4H6O4) is by definition a C4 dicarboxylic acid. E. coli is a prokaryotic organism.",
  },
  {
    element_number: 2,
    element_text:
      "wherein the microorganism has been genetically modified to overexpress at least one gene in the reductive TCA branch",
    status: "met",
    reasoning:
      "Standard bio-succinic acid production strains overexpress phosphoenolpyruvate carboxylase (ppc) and/or malate dehydrogenase (mdh), both of which are part of the reductive TCA branch. The compound producer's publicly available strain documentation confirms overexpression of ppc.",
    confidence: 0.88,
    evidence:
      "Published literature on FX060 and FX073 E. coli strains confirms overexpression of reductive TCA genes (Fictional Reference Alpha, Biotechnol Bioeng, 2008).",
  },
  {
    element_number: 3,
    element_text:
      "in a culture medium comprising a carbon source selected from glucose, glycerol, or sucrose at a concentration of 20-200 g/L",
    status: "met",
    reasoning:
      "The production protocol uses glucose at 100 g/L initial concentration, which falls within the claimed range of 20-200 g/L and is one of the enumerated carbon sources.",
    confidence: 0.92,
    evidence:
      "Process specification document indicates glucose feed at 100 g/L in the initial batch phase.",
  },
  {
    element_number: 4,
    element_text:
      "recovering the C4 dicarboxylic acid at a yield of at least 0.8 mol/mol carbon source",
    status: "not_met",
    reasoning:
      "The evaluated production process achieves a molar yield of approximately 0.65-0.72 mol succinic acid per mol glucose, which falls below the 0.8 mol/mol threshold specified in this claim element. However, yields are process-dependent and could potentially reach 0.8 mol/mol with optimized conditions.",
    confidence: 0.73,
    evidence:
      "Internal batch records from three production runs show yields of 0.65, 0.69, and 0.72 mol/mol respectively.",
  },
];

const CLAIM_ELEMENTS_MERIDIAN_DEP: ClaimElement[] = [
  {
    element_number: 1,
    element_text: "The method of claim 1",
    status: "partially_met",
    reasoning:
      "Dependent on claim 1, which has three of four elements met. The dependency is partially satisfied because element 4 of claim 1 is not met under current process conditions.",
    confidence: 0.75,
    evidence: "See analysis of claim 1 above.",
  },
  {
    element_number: 2,
    element_text:
      "wherein the microorganism further comprises a deletion of the ldhA gene encoding lactate dehydrogenase",
    status: "met",
    reasoning:
      "The E. coli production strain used in the evaluated process has a confirmed ldhA deletion to eliminate lactate as a byproduct, which is standard practice in succinate-producing strains.",
    confidence: 0.91,
    evidence:
      "Strain genotype records confirm \u0394ldhA. This deletion is also documented in Fictional Reference Alpha (2008) for the parent FX060 strain.",
  },
];

const CLAIM_ELEMENTS_MERIDIAN_DEP2: ClaimElement[] = [
  {
    element_number: 1,
    element_text: "The method of claim 1",
    status: "partially_met",
    reasoning: "As with claim 2, dependent on partially satisfied claim 1.",
    confidence: 0.75,
    evidence: "See analysis of claim 1.",
  },
  {
    element_number: 2,
    element_text:
      "wherein the fermentation is conducted under anaerobic or microaerobic conditions at a pH of 5.5-7.5",
    status: "met",
    reasoning:
      "The production process operates under dual-phase conditions with the production phase being anaerobic at pH 6.5-7.0, which is within the claimed range.",
    confidence: 0.87,
    evidence:
      "Process control records show pH maintained at 6.8 \u00b1 0.2 under anaerobic production phase.",
  },
];

const PATENT_ANALYSIS_MERIDIAN: PatentAnalysis = {
  patent_id: "US0000000001A1",
  title:
    "Methods for producing C4 dicarboxylic acids using engineered prokaryotic microorganisms",
  assignee: "Fictional Meridian Therapeutics",
  expiry_date: "2035-06-14",
  claims_analyzed: [
    {
      claim_number: 1,
      claim_type: "independent",
      depends_on: null,
      preamble: "A method for producing a C4 dicarboxylic acid",
      transitional_phrase: "comprising",
      elements: CLAIM_ELEMENTS_MERIDIAN,
      overall_status: "partially_met",
      overall_confidence: 0.87,
      reasoning:
        "Three of four elements are met. The yield limitation (element 4) requiring \u22650.8 mol/mol is the only unmet element. Current process yields of 0.65-0.72 mol/mol fall short but are close enough that process optimization or doctrine of equivalents could close the gap.",
    },
    {
      claim_number: 2,
      claim_type: "dependent",
      depends_on: 1,
      preamble: "The method of claim 1",
      transitional_phrase: "wherein",
      elements: CLAIM_ELEMENTS_MERIDIAN_DEP,
      overall_status: "partially_met",
      overall_confidence: 0.83,
      reasoning:
        "Dependent claim 2 adds a temperature range limitation (30-40\u00b0C) that is met by the standard 37\u00b0C fermentation. The additional limitation does not reduce risk since the independent claim elements are the controlling factor.",
    },
    {
      claim_number: 5,
      claim_type: "dependent",
      depends_on: 1,
      preamble: "The method of claim 1",
      transitional_phrase: "wherein",
      elements: CLAIM_ELEMENTS_MERIDIAN_DEP2,
      overall_status: "partially_met",
      overall_confidence: 0.81,
      reasoning:
        "Dependent claim 5 requires anaerobic conditions during the production phase. The evaluated process uses anaerobic production, so this limitation is met. Risk is marginally lower than claim 1 only because the additional limitation is independently met.",
    },
  ],
  risk_level: "high",
  risk_summary:
    "Three of four elements of independent claim 1 are met. The yield limitation (element 4) is currently not met but is within reach of process optimization. Dependent claims 2 and 5 add limitations that are met, meaning the overall risk remains high if production yields improve or if a court applies the doctrine of equivalents to the yield gap.",
  design_around_suggestions: [
    {
      element_avoided: 1,
      suggestion:
        "Use a eukaryotic host organism (e.g., Saccharomyces cerevisiae or Yarrowia lipolytica) instead of a prokaryotic microorganism to fall outside the claim scope, which is limited to prokaryotic hosts.",
      feasibility:
        "Moderate. Yeast-based succinic acid production has been demonstrated at pilot scale by Fictional Riverglass (Fictional Orbit/River joint venture) using S. cerevisiae.",
    },
    {
      element_avoided: 4,
      suggestion:
        "Maintain production yields below 0.8 mol/mol by limiting carbon source utilization, though this reduces process economics.",
      feasibility:
        "Low. Operating below optimal yield is economically disadvantageous and would likely be viewed as intentional design-around rather than a genuine process distinction.",
    },
  ],
  orange_book_info: null,
  model_used: "claude-sonnet-4-20250514",
  thinking_text:
    "This patent presents a significant FTO concern. The independent claim is broadly drafted to cover any recombinant prokaryotic host producing C4 dicarboxylic acids via overexpression of reductive TCA genes. Three of four elements are clearly satisfied by a standard bio-succinic acid process. The yield limitation of 0.8 mol/mol provides the primary basis for non-infringement, but current process yields of 0.65-0.72 are close enough that process optimization or measurement variability could push yields into the infringing range. Recommending high risk with design-around focus on host organism switch.",
  input_tokens: 8432,
  output_tokens: 2187,
};

const PATENT_ANALYSIS_ATLAS: PatentAnalysis = {
  patent_id: "US0000000002A1",
  title:
    "Process for purification and crystallization of bio-based succinic acid from fermentation broth",
  assignee: "Fictional Atlas Chemistry",
  expiry_date: "2033-11-22",
  claims_analyzed: [
    {
      claim_number: 1,
      claim_type: "independent",
      depends_on: null,
      preamble: "A process for purifying succinic acid",
      transitional_phrase: "comprising",
      elements: [
        {
          element_number: 1,
          element_text:
            "acidifying a fermentation broth containing succinic acid to a pH below 2.5 using a mineral acid",
          status: "met",
          reasoning:
            "The evaluated downstream process acidifies clarified broth to pH 2.0 using sulfuric acid (a mineral acid) to precipitate proteins and convert succinate salts to free acid form.",
          confidence: 0.93,
          evidence:
            "DSP protocol specifies acidification to pH 2.0 \u00b1 0.1 with H2SO4.",
        },
        {
          element_number: 2,
          element_text:
            "crystallizing the succinic acid by cooling the acidified broth from a temperature of at least 60\u00b0C to below 10\u00b0C at a controlled cooling rate of 0.5-5\u00b0C per minute",
          status: "met",
          reasoning:
            "The production process uses cooling crystallization from 70\u00b0C to 4\u00b0C with a programmed cooling ramp of approximately 2\u00b0C per minute, which falls within the claimed range.",
          confidence: 0.86,
          evidence:
            "Crystallizer logs show cooling from 68-72\u00b0C to 3-5\u00b0C at 1.8-2.2\u00b0C/min across five batches.",
        },
        {
          element_number: 3,
          element_text:
            "recovering crystalline succinic acid having a purity of at least 99.5% by weight",
          status: "partially_met",
          reasoning:
            "Final product purity averages 99.2-99.6% across recent batches. Some batches meet the 99.5% threshold while others fall slightly below. This element is partially met given the inconsistency.",
          confidence: 0.68,
          evidence:
            "HPLC certificates of analysis for lots SA-2025-001 through SA-2025-012 show purity range of 99.18-99.62%.",
        },
      ],
      overall_status: "partially_met",
      overall_confidence: 0.82,
      reasoning:
        "Both key process elements (acidification and crystallization) are met. The purity threshold of 99.5% is partially met with inconsistent batch results, making this a borderline infringement case.",
    },
    {
      claim_number: 3,
      claim_type: "dependent",
      depends_on: 1,
      preamble: "The process of claim 1",
      transitional_phrase: "further comprising",
      elements: [
        {
          element_number: 1,
          element_text: "The process of claim 1",
          status: "partially_met",
          reasoning: "Dependent on claim 1, which is partially met.",
          confidence: 0.82,
          evidence: "See claim 1 analysis.",
        },
        {
          element_number: 2,
          element_text:
            "treating the acidified broth with activated carbon prior to crystallization to remove colored impurities",
          status: "met",
          reasoning:
            "The DSP protocol includes an activated carbon treatment step (2% w/v Norit SX Ultra) between acidification and crystallization, performed at 50\u00b0C for 30 minutes.",
          confidence: 0.94,
          evidence:
            "DSP batch records confirm activated carbon treatment at 2% w/v loading, 50\u00b0C, 30 min contact time.",
        },
      ],
      overall_status: "partially_met",
      overall_confidence: 0.8,
      reasoning:
        "Dependent claim 3 adds an activated carbon treatment step that is fully met by the evaluated process. Risk remains tied to the independent claim 1 analysis.",
    },
  ],
  risk_level: "high",
  risk_summary:
    "The cooling crystallization process used for succinic acid purification closely matches the claimed process. All key parameters (pH, temperature range, cooling rate) fall within the claim limitations. Product purity inconsistently meets the 99.5% threshold, making this a borderline case that could go either way in litigation.",
  design_around_suggestions: [
    {
      element_avoided: 2,
      suggestion:
        "Switch to reactive extraction with tri-n-octylamine (TOA) in 1-octanol as an alternative to cooling crystallization. This avoids the crystallization step entirely.",
      feasibility:
        "High. Reactive extraction of succinic acid with TOA is well-established (fictional recovery scenario, 2010) and is used commercially by at least two producers.",
    },
    {
      element_avoided: 1,
      suggestion:
        "Use an organic acid (e.g., citric acid) instead of a mineral acid for pH adjustment to fall outside the claim limitation specifying mineral acid.",
      feasibility:
        "Low. Citric acid would introduce additional organic acid impurities and complicate downstream separation.",
    },
  ],
  orange_book_info: null,
  model_used: "claude-sonnet-4-20250514",
  thinking_text:
    "The Fictional Atlas crystallization patent is concerning because the claim parameters closely match standard industrial practice for bio-succinic acid purification. The purity limitation provides some breathing room since not all batches reach 99.5%, but this is not a reliable basis for non-infringement. The strongest design-around is switching to reactive extraction.",
  input_tokens: 6218,
  output_tokens: 1843,
};

const PATENT_ANALYSIS_NOVA: PatentAnalysis = {
  patent_id: "US0000000003A1",
  title:
    "Engineered fungal strains for enzymatic conversion of fumaric acid to succinic acid",
  assignee: "Fictional Nova Enzymes",
  expiry_date: "2034-03-08",
  claims_analyzed: [
    {
      claim_number: 1,
      claim_type: "independent",
      depends_on: null,
      preamble: "An engineered Aspergillus niger strain",
      transitional_phrase: "comprising",
      elements: [
        {
          element_number: 1,
          element_text:
            "one or more heterologous nucleic acid sequences encoding a fumarase variant having at least 90% sequence identity to SEQ ID NO: 1",
          status: "not_met",
          reasoning:
            "The evaluated production process uses E. coli, not Aspergillus niger, and does not involve heterologous fumarase expression. The metabolic pathway to succinate does not proceed through fumaric acid as a deliberate intermediate.",
          confidence: 0.91,
          evidence:
            "The production strain is E. coli with native fumarase activity; no heterologous fumarase has been introduced.",
        },
        {
          element_number: 2,
          element_text:
            "wherein the strain produces succinic acid at a titer of at least 40 g/L when cultured with fumaric acid as a substrate",
          status: "not_met",
          reasoning:
            "The process uses glucose, not fumaric acid, as the primary carbon source. This element is not met.",
          confidence: 0.95,
          evidence:
            "Process documentation confirms glucose as sole carbon source.",
        },
      ],
      overall_status: "not_met",
      overall_confidence: 0.93,
      reasoning:
        "Neither element is met. The evaluated process uses a completely different organism (E. coli vs. A. niger) and does not involve heterologous fumarase or fumaric acid as a substrate.",
    },
    {
      claim_number: 8,
      claim_type: "independent",
      depends_on: null,
      preamble:
        "A method of producing succinic acid from a C4 dicarboxylic acid precursor",
      transitional_phrase: "comprising",
      elements: [
        {
          element_number: 1,
          element_text:
            "contacting fumaric acid with a cell-free extract of a fungal strain expressing a fumarase variant",
          status: "not_met",
          reasoning:
            "The evaluated process is a whole-cell fermentation, not a cell-free enzymatic conversion, and does not use fumaric acid as a substrate.",
          confidence: 0.94,
          evidence:
            "Production is whole-cell E. coli fermentation with glucose.",
        },
        {
          element_number: 2,
          element_text:
            "at a temperature of 30-55\u00b0C and pH 5.0-8.0 for a period of 2-48 hours",
          status: "partially_met",
          reasoning:
            "While the fermentation temperature (37\u00b0C) and pH (6.8) fall within these ranges, the process is fundamentally different from the claimed cell-free enzymatic conversion. The overlap is coincidental rather than substantive.",
          confidence: 0.62,
          evidence:
            "Process operates at 37\u00b0C, pH 6.8, 48-72h fermentation, but as a whole-cell process.",
        },
      ],
      overall_status: "not_met",
      overall_confidence: 0.88,
      reasoning:
        "The cell-free enzymatic conversion is fundamentally different from whole-cell fermentation. Temperature/pH overlap is coincidental. However, interpretive ambiguity around fumarate as an intracellular intermediate creates medium risk.",
    },
  ],
  risk_level: "medium",
  risk_summary:
    "The claims are directed to a fundamentally different production approach (enzymatic conversion of fumaric acid using engineered fungal strains). However, claim 8 covers a broader method involving C4 dicarboxylic acid precursors. If succinic acid production through the reductive TCA pathway is construed as involving fumaric acid as an intermediate, there could be some overlap. Rated medium due to this interpretive ambiguity.",
  design_around_suggestions: [
    {
      element_avoided: 1,
      suggestion:
        "Ensure production pathway documentation clearly demonstrates that fumaric acid is not used as a deliberate substrate or intermediate in the succinic acid production process.",
      feasibility:
        "High. This is primarily a documentation and claim construction issue rather than a process change.",
    },
  ],
  orange_book_info: null,
  model_used: "claude-sonnet-4-20250514",
  thinking_text:
    "The Fictional Nova patent is focused on a different production paradigm \u2014 enzymatic conversion of fumaric acid rather than fermentative production from sugars. The risk here is primarily interpretive: could a court construe the reductive TCA pathway as proceeding through fumaric acid as a precursor? In the reductive branch, oxaloacetate is converted to malate then fumarate then succinate, so fumarate is technically an intracellular intermediate. This creates some uncertainty, though the claim language focuses on fumaric acid as a substrate, not an intermediate.",
  input_tokens: 5891,
  output_tokens: 1562,
};

const PATENT_ANALYSIS_ORBIT: PatentAnalysis = {
  patent_id: "US0000000013A1",
  title:
    "Low-pH yeast fermentation process for organic acid production with in situ product removal",
  assignee: "Fictional Orbit Fermentation",
  expiry_date: "2031-08-19",
  claims_analyzed: [
    {
      claim_number: 1,
      claim_type: "independent",
      depends_on: null,
      preamble:
        "A continuous fermentation process for producing an organic acid",
      transitional_phrase: "comprising",
      elements: [
        {
          element_number: 1,
          element_text:
            "culturing a yeast strain of Saccharomyces cerevisiae at a pH below 3.0",
          status: "not_met",
          reasoning:
            "The evaluated process uses E. coli (a bacterium, not yeast) at pH 6.8, not S. cerevisiae at pH < 3.0. Neither the organism nor the pH condition is met.",
          confidence: 0.97,
          evidence: "Production organism is E. coli; operating pH is 6.8.",
        },
        {
          element_number: 2,
          element_text:
            "continuously removing the organic acid product using an integrated membrane separation unit",
          status: "not_met",
          reasoning:
            "The production process is a batch or fed-batch operation, not continuous. There is no integrated membrane separation for in situ product removal.",
          confidence: 0.96,
          evidence:
            "Process operates in fed-batch mode with downstream recovery after fermentation completion.",
        },
        {
          element_number: 3,
          element_text:
            "wherein the organic acid is selected from succinic acid, fumaric acid, malic acid, or itaconic acid",
          status: "met",
          reasoning:
            "Succinic acid is explicitly listed as one of the claimed organic acids.",
          confidence: 0.99,
          evidence: "Claim language expressly recites succinic acid.",
        },
      ],
      overall_status: "not_met",
      overall_confidence: 0.95,
      reasoning:
        "Two of three elements are unmet. The process uses E. coli (not yeast) in batch mode (not continuous) at neutral pH (not <3.0). Only the product identity (succinic acid) matches.",
    },
  ],
  risk_level: "low",
  risk_summary:
    "Although the claim recites succinic acid as a target product, the process limitations (S. cerevisiae, pH < 3.0, continuous fermentation with membrane separation) are all unmet by the evaluated E. coli batch process. Risk is low.",
  design_around_suggestions: [],
  orange_book_info: null,
  model_used: "claude-sonnet-4-20250514",
  thinking_text:
    "Clear non-infringement on two of three elements. The Fictional Orbit patent is focused on a fundamentally different process configuration. No design-around needed.",
  input_tokens: 4203,
  output_tokens: 987,
};

const PATENT_ANALYSIS_MYRIA: PatentAnalysis = {
  patent_id: "US0000000012A1",
  title: "Electrochemical reduction of CO2 to produce C2-C4 carboxylic acids",
  assignee: "Fictional Myria Corporation",
  expiry_date: "2030-02-11",
  claims_analyzed: [
    {
      claim_number: 1,
      claim_type: "independent",
      depends_on: null,
      preamble:
        "An electrochemical process for producing a C2-C4 carboxylic acid",
      transitional_phrase: "comprising",
      elements: [
        {
          element_number: 1,
          element_text:
            "reducing carbon dioxide at a cathode comprising a metal catalyst selected from copper, tin, or bismuth in an aqueous electrolyte",
          status: "not_met",
          reasoning:
            "The evaluated production process is a biological fermentation, not an electrochemical reduction. No cathode, metal catalyst, or electrolyte is involved.",
          confidence: 0.99,
          evidence:
            "The production method is microbial fermentation; no electrochemical components are present in the process.",
        },
      ],
      overall_status: "not_met",
      overall_confidence: 0.99,
      reasoning:
        "Complete non-overlap. Electrochemical CO2 reduction has zero common elements with biological fermentation. Clear of any infringement risk.",
    },
  ],
  risk_level: "clear",
  risk_summary:
    "This patent covers an entirely different production modality (electrochemical CO2 reduction) that has no overlap with biological fermentation. Clear of infringement concerns.",
  design_around_suggestions: [],
  orange_book_info: null,
  model_used: "claude-sonnet-4-20250514",
  thinking_text:
    "No overlap whatsoever. Electrochemical CO2 reduction is fundamentally different from biological fermentation.",
  input_tokens: 3102,
  output_tokens: 654,
};

const PATENT_ANALYSES: PatentAnalysis[] = [
  PATENT_ANALYSIS_MERIDIAN,
  PATENT_ANALYSIS_ATLAS,
  PATENT_ANALYSIS_NOVA,
  PATENT_ANALYSIS_ORBIT,
  PATENT_ANALYSIS_MYRIA,
];

// ── Doctrine-of-Equivalents assessments ─────────────────────────────────

const DOE_ASSESSMENTS: DoEAssessment[] = [
  {
    patent_id: "US0000000001A1",
    claim_number: 1,
    element_number: 4,
    element_text:
      "recovering the C4 dicarboxylic acid at a yield of at least 0.8 mol/mol carbon source",
    estoppel: {
      amendments_found: [
        "Amendment A filed 2020-03-15: narrowed yield limitation from 0.5 to 0.8 mol/mol in response to prior art rejection citing Fictional Reference Beta",
      ],
      estoppel_applies: true,
      surrendered_scope:
        "The applicant narrowed the yield limitation from 0.5 to 0.8 mol/mol during prosecution, surrendering coverage of processes with yields in the 0.5-0.8 range. This narrowing creates prosecution history estoppel that limits the application of the doctrine of equivalents for yields below 0.8 mol/mol.",
      file_wrapper_available: true,
      rejections_found: [
        "Non-final rejection (2019-11-22) under 35 U.S.C. \u00a7103: Examiner combined Fictional Reference Beta (Appl Environ Microbiol, 2002) with Fictional Reference Alpha (Biotechnol Bioeng, 2008) to reject original claim reciting 0.5 mol/mol yield.",
      ],
      prosecution_narrowing_count: 1,
    },
    fwr: {
      same_function: true,
      function_reasoning:
        "Both the claimed yield of 0.8 mol/mol and the actual yield of 0.65-0.72 mol/mol serve the same function: producing succinic acid from glucose with high carbon efficiency.",
      same_way: true,
      way_reasoning:
        "The biological pathway is identical \u2014 reductive TCA branch in E. coli. The difference in yield arises from process optimization (media composition, dissolved CO2, pH control), not from a fundamentally different approach.",
      same_result: false,
      result_reasoning:
        "The result differs quantitatively. A yield of 0.65-0.72 mol/mol represents a 9-19% lower carbon efficiency compared to the claimed 0.8 mol/mol. This difference is commercially significant (lower product per unit feedstock) and would likely be considered a different result by the court.",
      equivalent: false,
      chemical_context: {
        structural_relationship: "none",
        relationship_reasoning:
          "The yield limitation is a process parameter, not a structural limitation. Chemical equivalence concepts do not directly apply.",
        known_interchangeability: false,
        interchangeability_evidence: "",
      },
    },
    overall_equivalent: false,
    confidence: 0.78,
    confidence_band: "MODERATE",
    reasoning:
      "Although the function and way prongs are satisfied, the result prong fails because there is a meaningful quantitative difference between the actual yield (0.65-0.72) and the claimed yield (0.8). Moreover, prosecution history estoppel applies because the applicant narrowed the yield limitation from 0.5 to 0.8 during prosecution to overcome a prior art rejection. This estoppel bars application of the doctrine of equivalents for yields below 0.8 mol/mol, which includes the evaluated process.",
  },
  {
    patent_id: "US0000000002A1",
    claim_number: 1,
    element_number: 3,
    element_text:
      "recovering crystalline succinic acid having a purity of at least 99.5% by weight",
    estoppel: {
      amendments_found: [],
      estoppel_applies: false,
      surrendered_scope: "",
      file_wrapper_available: true,
      rejections_found: [
        "Non-final rejection (2018-07-03) under 35 U.S.C. \u00a7102(a)(1): Examiner cited Fictional Reference Gamma (Chem Eng Technol, 2008). Applicant argued distinction based on specific cooling rate limitations without amending the purity claim element.",
      ],
      prosecution_narrowing_count: 0,
    },
    fwr: {
      same_function: true,
      function_reasoning:
        "Both the claimed purity (\u226599.5%) and the actual purity (99.2-99.6%) serve the same function: providing high-purity succinic acid suitable for polymer-grade or pharmaceutical applications.",
      same_way: true,
      way_reasoning:
        "The purification is achieved by the same crystallization method. The minor purity difference reflects batch-to-batch variation, not a different purification approach.",
      same_result: true,
      result_reasoning:
        "The purity difference (99.2% vs 99.5%) is within normal analytical variability and both purities would be considered suitable for the same downstream applications. The result is substantially the same.",
      equivalent: true,
      chemical_context: {
        structural_relationship: "none",
        relationship_reasoning:
          "This is a process purity parameter, not a structural distinction.",
        known_interchangeability: true,
        interchangeability_evidence:
          "USP and EP monographs for succinic acid specify purity \u226599.0%, indicating that both 99.2% and 99.5% are considered pharmaceutical grade.",
      },
    },
    overall_equivalent: true,
    confidence: 0.72,
    confidence_band: "MODERATE",
    reasoning:
      "The function-way-result test is satisfied for the purity limitation. The difference between 99.2% and 99.5% purity is insubstantial \u2014 both values produce polymer- and pharmaceutical-grade succinic acid. No prosecution history estoppel applies because the patentee did not narrow the purity limitation during prosecution. A court would likely find that batches achieving 99.2% purity infringe under the doctrine of equivalents.",
  },
  {
    patent_id: "US0000000001A1",
    claim_number: 5,
    element_number: 1,
    element_text: "The method of claim 1",
    estoppel: {
      amendments_found: [
        "Amendment A filed 2020-03-15: narrowed yield limitation in parent claim 1.",
      ],
      estoppel_applies: true,
      surrendered_scope:
        "Estoppel from the amendment to claim 1 propagates to this dependent claim.",
      file_wrapper_available: true,
      rejections_found: [],
      prosecution_narrowing_count: 1,
    },
    fwr: null,
    overall_equivalent: false,
    confidence: 0.81,
    confidence_band: "HIGH",
    reasoning:
      "Prosecution history estoppel from the amendment to independent claim 1 propagates to this dependent claim. The analysis of the yield element (claim 1, element 4) applies equally here. No separate FWR analysis is warranted because estoppel is dispositive.",
  },
];

// ── Invalidity assessments ──────────────────────────────────────────────

const INVALIDITY_ASSESSMENTS: InvalidityAssessment[] = [
  {
    patent_id: "US0000000001A1",
    claim_numbers: [1, 2, 5],
    ptab: {
      has_been_challenged: true,
      proceedings: [
        {
          proceeding_number: "IPR0000-00001",
          type: "IPR",
          status: "Denied institution",
          filing_date: "2021-02-15",
          decision_date: "2021-08-22",
          claims_challenged: [1, 2, 3, 5],
          claims_cancelled: [],
          claims_survived: [1, 2, 3, 5],
          outcome_summary:
            "The Board denied institution finding that petitioner (Fictional GreenChem LLC) did not demonstrate a reasonable likelihood of prevailing on any challenged claim. The Board found that the prior art combination of Fictional Beta and Fictional Alpha did not disclose the yield limitation of 0.8 mol/mol and that the petitioner failed to provide sufficient motivation to combine.",
        },
      ],
      all_claims_cancelled: [],
    },
    prior_art: [
      {
        reference_id: "fictional-beta-2002",
        title: "Fictional process-study scenario Beta",
        publication_date: "2002-09-01",
        relevance:
          "Discloses E. coli fermentation for succinate production using glucose as carbon source, with yields up to 0.66 mol/mol under optimized dual-phase conditions. Teaches overexpression of ppc in the reductive TCA branch.",
        anticipation_score: 0.42,
        obviousness_score: 0.71,
        reference_type: "journal_article",
        authors: [
          "Fictional Researcher Beta",
          "Fictional Researcher Beta-Two",
          "Fictional Researcher Beta-Three",
        ],
        journal: "Fictional Journal of Process Research",
        doi: "",
        url: "https://example.invalid/prior-art/fictional-beta",
        abstract:
          "Dual-phase Escherichia coli fermentation was investigated for succinate production. Maximum succinate yields of 0.66 mol/mol glucose were achieved when the shift to anaerobic conditions was performed at an OD600 of 15.",
        source_database: "semantic_scholar",
      },
      {
        reference_id: "fictional-alpha-2008",
        title: "Fictional metabolic-engineering scenario Alpha",
        publication_date: "2008-05-01",
        relevance:
          "Describes E. coli strains FX060 and FX073 with deletions in ldhA, adhE, ackA, focA, and pflB, achieving succinate yields of 1.0-1.2 mol/mol glucose. Teaches the genetic modifications recited in claims 1 and 2.",
        anticipation_score: 0.65,
        obviousness_score: 0.82,
        reference_type: "journal_article",
        authors: [
          "Fictional Researcher Alpha",
          "Fictional Researcher Alpha-Two",
          "Fictional Researcher Alpha-Three",
          "Fictional Researcher Alpha-Four",
          "Fictional Researcher Alpha-Five",
          "Fictional Researcher Alpha-Six",
          "Fictional Researcher Alpha-Seven",
        ],
        journal: "Fictional Journal of Process Research",
        doi: "",
        url: "https://example.invalid/prior-art/fictional-alpha",
        abstract:
          "Metabolically engineered E. coli strains FX060 and FX073 were developed for succinate production. FX073 achieved a yield of 1.2 mol succinate per mol glucose in mineral salts medium under anaerobic conditions.",
        source_database: "semantic_scholar",
      },
      {
        reference_id: "US0000000014A1",
        title: "Fictional patent-reference scenario Epsilon",
        publication_date: "2007-05-29",
        relevance:
          "Patent by Fictional Southern Institute disclosing recombinant E. coli strains with overexpressed ppc and deleted ldhA for succinate production. Filing date predates the Fictional Meridian patent priority date.",
        anticipation_score: 0.58,
        obviousness_score: 0.76,
        reference_type: "patent",
        authors: [
          "Fictional Researcher Beta-Two",
          "Fictional Researcher Beta-Three",
          "Fictional Researcher Beta",
        ],
        journal: "",
        doi: "",
        url: "https://example.invalid/prior-art/fictional-epsilon",
        abstract:
          "Methods for producing succinate using recombinant E. coli with enhanced expression of phosphoenolpyruvate carboxylase and deletion of lactate dehydrogenase.",
        source_database: "bigquery",
      },
    ],
    written_description_issues: [
      "The specification provides only three working examples with yields of 0.82, 0.85, and 0.91 mol/mol. The claimed range of 'at least 0.8 mol/mol' is open-ended and may lack adequate written description support for very high yields (>1.5 mol/mol) that exceed the theoretical maximum.",
    ],
    claim_charts: [
      {
        patent_id: "US0000000001A1",
        claim_number: 1,
        prior_art_reference_id: "fictional-alpha-2008",
        entries: [
          {
            element_number: 1,
            element_text:
              "A method for producing a C4 dicarboxylic acid comprising culturing a recombinant prokaryotic microorganism",
            prior_art_reference_id: "fictional-alpha-2008",
            prior_art_disclosure:
              "Fictional Reference Alpha discloses metabolically engineered E. coli strains (recombinant prokaryotic microorganisms) for producing succinate (a C4 dicarboxylic acid).",
            citation_location: "Abstract; Materials and Methods, p. 301",
            disclosed: "yes",
            notes: "",
          },
          {
            element_number: 2,
            element_text:
              "wherein the microorganism has been genetically modified to overexpress at least one gene in the reductive TCA branch",
            prior_art_reference_id: "fictional-alpha-2008",
            prior_art_disclosure:
              "The FX073 strain was derived through metabolic evolution after deletion of competing pathways, resulting in enhanced flux through the reductive TCA branch. However, overexpression of specific reductive TCA genes was not explicitly performed.",
            citation_location: "Results, p. 303-304; Table 1",
            disclosed: "partial",
            notes:
              "Fictional Alpha achieves enhanced reductive TCA flux through gene deletions and metabolic evolution rather than through explicit overexpression of reductive TCA genes. Whether this constitutes 'genetic modification to overexpress' is a claim construction question.",
          },
          {
            element_number: 3,
            element_text:
              "in a culture medium comprising a carbon source selected from glucose, glycerol, or sucrose at a concentration of 20-200 g/L",
            prior_art_reference_id: "fictional-alpha-2008",
            prior_art_disclosure:
              "Fermentations were conducted in fictional mineral salts medium with 100 g/L glucose.",
            citation_location: "Materials and Methods, p. 301",
            disclosed: "yes",
            notes: "",
          },
          {
            element_number: 4,
            element_text:
              "recovering the C4 dicarboxylic acid at a yield of at least 0.8 mol/mol carbon source",
            prior_art_reference_id: "fictional-alpha-2008",
            prior_art_disclosure:
              "FX073 achieved succinate yields of 1.0-1.2 mol/mol glucose, exceeding the 0.8 mol/mol threshold.",
            citation_location: "Table 2; Results, p. 305",
            disclosed: "yes",
            notes:
              "This disclosure likely motivated the examiner to require the yield amendment from 0.5 to 0.8 mol/mol during prosecution.",
          },
        ],
        all_elements_disclosed: false,
        chart_summary:
          "Three of four elements are explicitly disclosed by Fictional Reference Alpha Element 2 is partially disclosed \u2014 enhanced reductive TCA flux is achieved through gene deletion and evolution rather than explicit gene overexpression. An obviousness argument combining Fictional Alpha (elements 1, 3, 4) with Fictional Beta (element 2, teaching ppc overexpression) is strong.",
      },
    ],
    graham_factors: {
      scope_and_content:
        "The prior art as of the effective filing date (2015-06-14) extensively documented E. coli metabolic engineering for succinate production. Key references include Fictional Beta (2002), Fictional Alpha (2008), and a fictional fifth reference (2005). The field was well-established with multiple groups publishing on reductive TCA pathway optimization.",
      differences_from_prior_art:
        "The primary difference between the claimed method and the prior art is the combination of (1) explicit overexpression of a reductive TCA gene with (2) a yield threshold of 0.8 mol/mol in a single process. Fictional Alpha achieved >0.8 mol/mol yields but through gene deletions rather than overexpression. Fictional Beta taught overexpression but achieved only 0.66 mol/mol yields.",
      level_of_ordinary_skill:
        "A person of ordinary skill would hold a Ph.D. in metabolic engineering, microbiology, or biochemical engineering with 2-3 years of experience in microbial strain development for organic acid production.",
      commercial_success:
        "Bio-succinic acid has achieved commercial success through multiple ventures (Fictional BioWorks, Fictional Riverglass, Fictional Sunvale, Fictional Myria), though market adoption has been slower than initial projections due to low petroleum prices.",
      long_felt_need:
        "There was a recognized need for bio-based succinic acid production to replace petrochemical routes. This need was documented in a fictional 2004 industry scenario.",
      failure_of_others:
        "Several companies (Fictional BioWorks, Fictional Myria) struggled to achieve consistent yields above 0.8 mol/mol at commercial scale, suggesting some difficulty in achieving the claimed yield threshold.",
      unexpected_results:
        "The specification does not demonstrate any unexpected results compared to the prior art. The yields achieved (0.82-0.91 mol/mol) are incremental improvements over Fictional Alpha's results (1.0-1.2 mol/mol) and do not appear surprising to a person of ordinary skill.",
      overall_obviousness_assessment:
        "The claimed method would have been obvious to a person of ordinary skill. The combination of Fictional Beta (teaching ppc overexpression) with Fictional Alpha (teaching high-yield succinate production in E. coli) provides strong motivation to overexpress reductive TCA genes in high-yielding strains. The PTAB's denial of institution was based on insufficient petitioner briefing rather than a substantive finding of non-obviousness.",
    },
    enablement_screening: null,
    overall_invalidity_strength: "moderate",
    reasoning:
      "A combined obviousness argument under 35 U.S.C. \u00a7103 using Fictional Alpha and Fictional Beta has moderate strength. The claim chart shows that Fictional Alpha alone discloses three of four elements, and Fictional Beta fills the gap on element 2 (overexpression of reductive TCA genes). The prior IPR denial is a negative factor but was based on procedural grounds (insufficient petitioner briefing) rather than a substantive assessment of patentability. The written description issue regarding the open-ended yield claim provides an additional attack vector.",
    confidence: 0.64,
    confidence_band: "MODERATE",
    screening_disclaimer:
      "This is an automated preliminary screening and does not constitute legal advice. A qualified patent attorney should evaluate these invalidity arguments before relying on them in any legal proceeding.",
  },
  {
    patent_id: "US0000000002A1",
    claim_numbers: [1, 3],
    ptab: {
      has_been_challenged: false,
      proceedings: [],
      all_claims_cancelled: [],
    },
    prior_art: [
      {
        reference_id: "fictional-gamma-2008",
        title: "Fictional crystallization-review scenario Gamma",
        publication_date: "2008-03-01",
        relevance:
          "Describes crystallization of bio-based succinic acid from fermentation broth, including acidification with H2SO4 and cooling crystallization. Process parameters substantially overlap with the claimed method.",
        anticipation_score: 0.74,
        obviousness_score: 0.81,
        reference_type: "journal_article",
        authors: [
          "Fictional Researcher Gamma",
          "Fictional Researcher Gamma-Two",
          "Fictional Researcher Gamma-Three",
          "Fictional Researcher Gamma-Four",
          "Fictional Researcher Gamma-Five",
        ],
        journal: "Fictional Journal of Process Research",
        doi: "",
        url: "https://example.invalid/prior-art/fictional-gamma",
        abstract:
          "The production of succinic acid by fermentation and its subsequent purification by acidification and crystallization is reviewed. Cooling crystallization from acidified broth yielded succinic acid with >99% purity.",
        source_database: "semantic_scholar",
      },
      {
        reference_id: "fictional-delta-2010",
        title: "Fictional recovery-review scenario Delta",
        publication_date: "2010-07-15",
        relevance:
          "Comprehensive review of succinic acid recovery methods including crystallization, reactive extraction, and electrodialysis. Teaches acidification to pH 2.0 followed by cooling crystallization as a standard recovery approach.",
        anticipation_score: 0.55,
        obviousness_score: 0.72,
        reference_type: "journal_article",
        authors: [
          "Fictional Researcher Delta",
          "Fictional Researcher Delta-Two",
        ],
        journal: "Fictional Journal of Process Research",
        doi: "",
        url: "https://example.invalid/prior-art/fictional-delta",
        abstract:
          "Fictional recovery-review scenario Delta was reviewed. Crystallization after acidification, reactive extraction with tertiary amines, and electrodialysis were compared for yield and purity.",
        source_database: "openalex",
      },
    ],
    written_description_issues: [],
    claim_charts: [
      {
        patent_id: "US0000000002A1",
        claim_number: 1,
        prior_art_reference_id: "fictional-gamma-2008",
        entries: [
          {
            element_number: 1,
            element_text:
              "acidifying a fermentation broth containing succinic acid to a pH below 2.5 using a mineral acid",
            prior_art_reference_id: "fictional-gamma-2008",
            prior_art_disclosure:
              "Fictional Gamma describes acidification of fermentation broth with sulfuric acid to convert calcium succinate to free succinic acid at pH approximately 2.0.",
            citation_location: "Section 3.2, p. 1428; Figure 2",
            disclosed: "yes",
            notes: "",
          },
          {
            element_number: 2,
            element_text:
              "crystallizing the succinic acid by cooling the acidified broth from a temperature of at least 60\u00b0C to below 10\u00b0C at a controlled cooling rate of 0.5-5\u00b0C per minute",
            prior_art_reference_id: "fictional-gamma-2008",
            prior_art_disclosure:
              "Fictional Gamma describes cooling crystallization but does not specify a controlled cooling rate of 0.5-5\u00b0C/min. The reference describes 'gradual cooling' from 70\u00b0C to 5\u00b0C without specifying the exact rate.",
            citation_location: "Section 3.2, p. 1429",
            disclosed: "partial",
            notes:
              "The cooling rate is the primary distinction. However, cooling rates of 0.5-5\u00b0C/min are standard in industrial crystallization practice and would be obvious to a person of ordinary skill.",
          },
          {
            element_number: 3,
            element_text:
              "recovering crystalline succinic acid having a purity of at least 99.5% by weight",
            prior_art_reference_id: "fictional-gamma-2008",
            prior_art_disclosure:
              "Fictional Gamma reports purity of '>99%' for the crystallized product but does not specify whether 99.5% was achieved.",
            citation_location: "Section 3.2, p. 1429; Table 3",
            disclosed: "partial",
            notes:
              "The 0.5% purity gap between '>99%' and '\u226599.5%' is a narrow distinction that could be addressed through routine optimization.",
          },
        ],
        all_elements_disclosed: false,
        chart_summary:
          "Fictional Gamma discloses the core crystallization process but lacks specificity on cooling rate and the precise purity threshold. An anticipation argument is weak, but an obviousness argument is strong because the cooling rate and purity improvements are within routine optimization for a skilled crystallization engineer.",
      },
    ],
    graham_factors: {
      scope_and_content:
        "Crystallization of organic acids from fermentation broth was well-known in the art. The Fictional Gamma review and multiple textbooks on industrial crystallization document the basic process of acidification followed by cooling crystallization.",
      differences_from_prior_art:
        "The claimed process specifies a controlled cooling rate (0.5-5\u00b0C/min) and a purity threshold (99.5%) not explicitly disclosed in the prior art. These are quantitative refinements of known processes.",
      level_of_ordinary_skill:
        "A person of ordinary skill would hold a B.S. or M.S. in chemical engineering with 3-5 years of experience in industrial crystallization or organic acid downstream processing.",
      commercial_success:
        "Multiple companies have successfully commercialized bio-succinic acid purification using crystallization methods (Fictional Atlas/Fictional Purity Labs, Fictional Sunvale, Fictional BioWorks), suggesting commercial viability.",
      long_felt_need:
        "No specific long-felt need identified. Crystallization of succinic acid from fermentation broth is a well-practiced industrial technique.",
      failure_of_others:
        "No evidence of failure by others to achieve 99.5% purity through cooling crystallization. This purity level is routinely achievable.",
      unexpected_results:
        "The specification does not demonstrate any unexpected results from the claimed cooling rate range.",
      overall_obviousness_assessment:
        "The claimed process would have been obvious. Controlled cooling crystallization at specified rates is standard practice, and the 99.5% purity threshold is achievable through routine optimization of crystallization conditions.",
    },
    enablement_screening: {
      genus_claim_detected: true,
      genus_indicators: [
        "Claim recites 'a mineral acid' without limitation to a specific acid",
        "Cooling rate range of 0.5-5\u00b0C/min covers a 10\u00d7 range of conditions",
      ],
      specification_enables_full_scope: "yes",
      amgen_v_sanofi_flags: [],
      reasoning:
        "Although the claim contains genus terms, the specification provides working examples covering sulfuric acid, hydrochloric acid, and phosphoric acid at cooling rates of 1, 2, and 4\u00b0C/min. The genus is narrow and well-enabled across its scope.",
    },
    overall_invalidity_strength: "moderate-strong",
    reasoning:
      "An anticipation argument based on Fictional Gamma is moderately strong \u2014 the reference discloses the core process but lacks the specific cooling rate and purity values. An obviousness argument is strong because the specific cooling rate and purity are achievable through routine optimization by a skilled crystallization engineer. No PTAB challenges have been filed, meaning these arguments are untested. The enablement screening did not reveal significant issues.",
    confidence: 0.71,
    confidence_band: "MODERATE",
    screening_disclaimer:
      "This is an automated preliminary screening and does not constitute legal advice. A qualified patent attorney should evaluate these invalidity arguments before relying on them in any legal proceeding.",
  },
];

// ── Verification ────────────────────────────────────────────────────────

const VERIFICATION: VerificationResult = {
  checks: [
    {
      check_name: "citation_validity",
      passed: true,
      details:
        "The fictional report references are internally consistent and present in the sample record set. No live register check is claimed.",
      severity: "pass",
    },
    {
      check_name: "claim_grounding",
      passed: true,
      details:
        "The fictional claim excerpts and element mappings are linked inside the sample record. They are not published claim language.",
      severity: "pass",
    },
    {
      check_name: "entity_validation",
      passed: true,
      details:
        "The sample compound identifiers are internally consistent. The public sample does not claim a live external validation.",
      severity: "pass",
    },
    {
      check_name: "date_consistency",
      passed: true,
      details:
        "The fictional date relationships pass the sample's internal checks. They must not be used for a real expiry analysis.",
      severity: "pass",
    },
    {
      check_name: "risk_level_justification",
      passed: true,
      details:
        "The sample risk labels are consistent with its fictional element mapping. The labels prioritise review and do not mean legal clearance.",
      severity: "pass",
    },
    {
      check_name: "doe_consistency",
      passed: false,
      details:
        "The sample equivalence assessment conflicts with its fictional prosecution-history note. Manual review is required before relying on that part of the analysis.",
      severity: "warning",
    },
  ],
  all_citations_valid: true,
  all_claims_grounded: true,
  all_entities_valid: true,
  dates_consistent: true,
  risk_levels_justified: true,
  issues: [
    "The sample equivalence assessment may be overconfident because its fictional prosecution-history note was not fully resolved. Manual review is required.",
  ],
};

// ── Source health ───────────────────────────────────────────────────────

const SOURCE_HEALTH: SourceHealth = {
  entries: [
    {
      source: "pubchem_sdq",
      status: "ok",
      patent_count: 847,
      error_message: "",
    },
    {
      source: "surechembl",
      status: "ok",
      patent_count: 1203,
      error_message: "",
    },
    {
      source: "bigquery",
      status: "ok",
      patent_count: 312,
      error_message: "",
    },
    {
      source: "bigquery_annotations",
      status: "ok",
      patent_count: 55,
      error_message: "",
    },
    {
      source: "patcid",
      status: "failed",
      patent_count: 0,
      error_message:
        "ConnectionError: PatCID API returned HTTP 503 Service Unavailable after 3 retries with exponential backoff. Last attempt at 2026-03-08T14:23:45Z.",
    },
  ],
};

// ── Audit trail ─────────────────────────────────────────────────────────

const SEARCH_FUNNEL = [
  {
    patent_id: "US0000000001A1",
    sources_found_in: ["surechembl", "bigquery"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.91,
    bm25_score: 0.87,
    final_blend_score: 0.89,
    final_rank: 1,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000002A1",
    sources_found_in: ["surechembl", "bigquery", "pubchem"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.88,
    bm25_score: 0.82,
    final_blend_score: 0.85,
    final_rank: 2,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000003A1",
    sources_found_in: ["surechembl"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.76,
    bm25_score: 0.79,
    final_blend_score: 0.77,
    final_rank: 5,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000013A1",
    sources_found_in: ["bigquery"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.72,
    bm25_score: 0.68,
    final_blend_score: 0.7,
    final_rank: 8,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000012A1",
    sources_found_in: ["pubchem"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.64,
    bm25_score: 0.58,
    final_blend_score: 0.61,
    final_rank: 14,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000006A1",
    sources_found_in: ["surechembl", "pubchem"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.83,
    bm25_score: 0.76,
    final_blend_score: 0.8,
    final_rank: 3,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000004A1",
    sources_found_in: ["bigquery"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.81,
    bm25_score: 0.74,
    final_blend_score: 0.78,
    final_rank: 4,
    included_in_triage: true,
  },
  {
    patent_id: "EP0000001A1",
    sources_found_in: ["surechembl"],
    passed_hard_filter: false,
    filter_reason: "Non-US patent excluded from FTO analysis scope",
    composite_score: null,
    bm25_score: null,
    final_blend_score: null,
    final_rank: null,
    included_in_triage: false,
  },
  {
    patent_id: "US0000000015A1",
    sources_found_in: ["pubchem"],
    passed_hard_filter: false,
    filter_reason: "Patent expired (expiry date 2024-01-15)",
    composite_score: null,
    bm25_score: null,
    final_blend_score: null,
    final_rank: null,
    included_in_triage: false,
  },
  {
    patent_id: "US0000000005A1",
    sources_found_in: ["bigquery"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.74,
    bm25_score: 0.71,
    final_blend_score: 0.73,
    final_rank: 6,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000007A1",
    sources_found_in: ["surechembl"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.73,
    bm25_score: 0.69,
    final_blend_score: 0.71,
    final_rank: 7,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000010A1",
    sources_found_in: ["bigquery"],
    passed_hard_filter: false,
    filter_reason: "Application (not granted)",
    composite_score: null,
    bm25_score: null,
    final_blend_score: null,
    final_rank: null,
    included_in_triage: false,
  },
  {
    patent_id: "US0000000016A1",
    sources_found_in: ["pubchem", "surechembl"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.59,
    bm25_score: 0.53,
    final_blend_score: 0.56,
    final_rank: 18,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000009A1",
    sources_found_in: ["surechembl"],
    passed_hard_filter: true,
    filter_reason: "",
    composite_score: 0.55,
    bm25_score: 0.61,
    final_blend_score: 0.58,
    final_rank: 16,
    included_in_triage: true,
  },
  {
    patent_id: "US0000000017A1",
    sources_found_in: ["pubchem"],
    passed_hard_filter: false,
    filter_reason: "Patent expired (expiry date 2023-09-03)",
    composite_score: null,
    bm25_score: null,
    final_blend_score: null,
    final_rank: null,
    included_in_triage: false,
  },
];

const TRIAGE_AUDIT = [
  {
    patent_id: "US0000000001A1",
    relevance: "relevant",
    reason:
      "Claims directly cover microbial production of C4 dicarboxylic acids including succinic acid using recombinant E. coli. High blocking potential for bio-based succinic acid production.",
    confidence: 0.94,
    passed_triage: true,
  },
  {
    patent_id: "US0000000002A1",
    relevance: "relevant",
    reason:
      "Claims cover purification of bio-succinic acid by crystallization from fermentation broth. Directly relevant to downstream processing.",
    confidence: 0.91,
    passed_triage: true,
  },
  {
    patent_id: "US0000000003A1",
    relevance: "relevant",
    reason:
      "Claims cover enzymatic conversion to succinic acid using engineered fungal strains. Different production route but the method claims may overlap with reductive TCA pathway intermediates.",
    confidence: 0.78,
    passed_triage: true,
  },
  {
    patent_id: "US0000000013A1",
    relevance: "possibly_relevant",
    reason:
      "Claims cover low-pH yeast fermentation for organic acids including succinic acid. Different host organism but succinic acid is explicitly recited as a target product.",
    confidence: 0.62,
    passed_triage: true,
  },
  {
    patent_id: "US0000000012A1",
    relevance: "possibly_relevant",
    reason:
      "Claims cover electrochemical CO2 reduction to C2-C4 carboxylic acids. Different production modality but succinic acid falls within the claimed product scope.",
    confidence: 0.48,
    passed_triage: true,
  },
  {
    patent_id: "US0000000006A1",
    relevance: "not_relevant",
    reason:
      "Claims are limited to adipic acid (C6) production via engineered Candida tropicalis. No overlap with C4 dicarboxylic acid production.",
    confidence: 0.88,
    passed_triage: false,
  },
  {
    patent_id: "US0000000004A1",
    relevance: "not_relevant",
    reason:
      "Claims cover membrane electrodialysis for separation of amino acids from fermentation broth. Not applicable to succinic acid recovery.",
    confidence: 0.85,
    passed_triage: false,
  },
  {
    patent_id: "US0000000005A1",
    relevance: "not_relevant",
    reason:
      "Claims are directed to polybutylene succinate (PBS) polymerization, not to succinic acid monomer production. Different field of use.",
    confidence: 0.92,
    passed_triage: false,
  },
];

const ANALYSIS_AUDIT = [
  {
    patent_id: "US0000000001A1",
    selected_for_analysis: true,
    selection_reason:
      "Triage: relevant (0.94 confidence). Claims directly cover target compound production method.",
    risk_level: "high",
    selected_for_doe: true,
    selected_for_invalidity: true,
  },
  {
    patent_id: "US0000000002A1",
    selected_for_analysis: true,
    selection_reason:
      "Triage: relevant (0.91 confidence). Claims cover downstream processing of target compound.",
    risk_level: "high",
    selected_for_doe: true,
    selected_for_invalidity: true,
  },
  {
    patent_id: "US0000000003A1",
    selected_for_analysis: true,
    selection_reason:
      "Triage: relevant (0.78 confidence). Alternative production route with potential claim overlap.",
    risk_level: "medium",
    selected_for_doe: false,
    selected_for_invalidity: false,
  },
  {
    patent_id: "US0000000013A1",
    selected_for_analysis: true,
    selection_reason:
      "Triage: possibly_relevant (0.62 confidence). Succinic acid recited in claims despite different process.",
    risk_level: "low",
    selected_for_doe: false,
    selected_for_invalidity: false,
  },
  {
    patent_id: "US0000000012A1",
    selected_for_analysis: true,
    selection_reason:
      "Triage: possibly_relevant (0.48 confidence). Included for completeness as succinic acid is within the claimed product scope.",
    risk_level: "clear",
    selected_for_doe: false,
    selected_for_invalidity: false,
  },
];

const TIMING_DATA = [
  {
    step_name: "step1_resolve_compound",
    started_at: "2026-03-08T14:20:01.000Z",
    completed_at: "2026-03-08T14:20:02.200Z",
    duration_seconds: 1.2,
    items_processed: 1,
    items_output: 1,
  },
  {
    step_name: "step2_search_patents",
    started_at: "2026-03-08T14:20:02.200Z",
    completed_at: "2026-03-08T14:20:14.600Z",
    duration_seconds: 12.4,
    items_processed: 2417,
    items_output: 150,
  },
  {
    step_name: "step3_triage",
    started_at: "2026-03-08T14:20:14.600Z",
    completed_at: "2026-03-08T14:20:23.300Z",
    duration_seconds: 8.7,
    items_processed: 150,
    items_output: 47,
  },
  {
    step_name: "step4_analyze_claims",
    started_at: "2026-03-08T14:20:23.300Z",
    completed_at: "2026-03-08T14:21:08.500Z",
    duration_seconds: 45.2,
    items_processed: 5,
    items_output: 5,
  },
  {
    step_name: "step5_doe_assessment",
    started_at: "2026-03-08T14:21:08.500Z",
    completed_at: "2026-03-08T14:21:30.100Z",
    duration_seconds: 21.6,
    items_processed: 3,
    items_output: 3,
  },
  {
    step_name: "step6_invalidity_screening",
    started_at: "2026-03-08T14:21:30.100Z",
    completed_at: "2026-03-08T14:22:04.400Z",
    duration_seconds: 34.3,
    items_processed: 2,
    items_output: 2,
  },
  {
    step_name: "step7_verification",
    started_at: "2026-03-08T14:22:04.400Z",
    completed_at: "2026-03-08T14:22:09.800Z",
    duration_seconds: 5.4,
    items_processed: 6,
    items_output: 6,
  },
  {
    step_name: "step8_report_generation",
    started_at: "2026-03-08T14:22:09.800Z",
    completed_at: "2026-03-08T14:22:13.100Z",
    duration_seconds: 3.3,
    items_processed: 1,
    items_output: 1,
  },
];

const AUDIT_TRAIL: PipelineAuditTrail = {
  search_funnel: SEARCH_FUNNEL,
  triage_audit: TRIAGE_AUDIT,
  analysis_audit: ANALYSIS_AUDIT,
  timing_data: TIMING_DATA,
  total_patents_discovered: 2417,
  patents_after_hard_filter: 1893,
  patents_after_ranking: 150,
  patents_after_triage: 47,
  patents_analyzed: 5,
};

// ── Step token usage ────────────────────────────────────────────────────

const STEP_TOKEN_USAGE: StepTokenUsage[] = [
  {
    step_name: "triage",
    model_role: "claude-sonnet-4-20250514",
    input_tokens: 42380,
    output_tokens: 8920,
  },
  {
    step_name: "analyze",
    model_role: "claude-sonnet-4-20250514",
    input_tokens: 27846,
    output_tokens: 7233,
  },
  {
    step_name: "doe",
    model_role: "claude-sonnet-4-20250514",
    input_tokens: 18450,
    output_tokens: 5120,
  },
  {
    step_name: "invalidity",
    model_role: "claude-sonnet-4-20250514",
    input_tokens: 22190,
    output_tokens: 6840,
  },
  {
    step_name: "report",
    model_role: "claude-sonnet-4-20250514",
    input_tokens: 15280,
    output_tokens: 3450,
  },
];

// ── Patent narratives ──────────────────────────────────────────────────

const PATENT_NARRATIVES: Record<string, string> = {
  US0000000001A1:
    "This Fictional Meridian patent covers a broad method for producing C4 dicarboxylic acids via recombinant prokaryotic fermentation with overexpressed reductive TCA genes. Three of four independent claim elements are met by a standard bio-succinic acid process. The yield limitation (0.8 mol/mol) is the primary basis for non-infringement, but current yields of 0.65-0.72 are close to the threshold. Prosecution history estoppel limits doctrine of equivalents arguments on the yield element. An invalidity argument based on Fictional Alpha (2008) and Fictional Beta (2002) has moderate strength, though a prior IPR was denied institution.",
  US0000000002A1:
    "The Fictional Atlas crystallization patent claims a specific purification process for bio-succinic acid involving acidification, controlled cooling crystallization, and high-purity recovery. The evaluated downstream process matches the claimed parameters closely, with product purity borderline at the 99.5% threshold. Design-around via reactive extraction with TOA is the most feasible alternative. An invalidity argument based on Fictional Gamma (2008) is moderately strong, particularly for an obviousness challenge where the specific cooling rate and purity are routine optimization parameters.",
  US0000000003A1:
    "The Fictional Nova patent is directed to a distinct production approach using engineered Aspergillus niger strains for enzymatic conversion of fumaric acid to succinic acid. The evaluated E. coli fermentation process does not use fumaric acid as a substrate and does not involve fungal strains. However, the reductive TCA pathway does involve fumarate as an intracellular intermediate, creating some interpretive ambiguity. The risk is medium, primarily driven by claim construction uncertainty.",
  US0000000013A1:
    "Fictional Orbit's patent covers continuous low-pH yeast fermentation with in situ membrane separation for organic acid production. The evaluated process differs in organism (E. coli vs. S. cerevisiae), mode (batch vs. continuous), pH (6.8 vs. <3.0), and recovery method (no membrane separation). Risk is low with no design-around needed.",
  US0000000012A1:
    "Fictional Myria's electrochemical CO2 reduction patent has zero overlap with biological fermentation. The process modality is entirely different, and no claim elements are met. Risk is clear.",
};

// ── Analysis failures & data limitations ────────────────────────────────

const ANALYSIS_FAILURES: AnalysisFailure[] = [
  {
    patent_id: "US0000000005A1",
    step: "step4_analyze",
    error_type: "ClaudeValidationError",
    error_message:
      "LLM response failed schema validation after 3 retries. Claims text may contain non-standard formatting.",
    recoverable: false,
  },
  {
    patent_id: "US0000000008A1",
    step: "step5_doe",
    error_type: "TimeoutError",
    error_message:
      "USPTO file wrapper API timed out after 30s. Prosecution history unavailable for estoppel analysis.",
    recoverable: true,
  },
];

const DATA_LIMITATIONS: DataLimitation[] = [
  {
    category: "source_unavailable",
    description:
      "PatCID API returned 503 Service Unavailable. Structural similarity search results may be incomplete.",
    impact:
      "Structurally similar patents found only via SureChEMBL substructure search. Some relevant patents with Markush structures may have been missed.",
  },
  {
    category: "enrichment_gap",
    description:
      "BigQuery annotations quota exceeded. Chemical entity annotations from Google Patents could not be retrieved.",
    impact:
      "CPC code enrichment relied on EPO data only. Some patent classifications may be incomplete.",
  },
];

// ── Action items ────────────────────────────────────────────────────────

const ACTION_ITEMS: ActionItem[] = [
  {
    action_type: "design_around",
    priority: "critical",
    description:
      "Implement design-around for US0000000001A1 — 2 option(s) identified.",
    patent_ids: ["US0000000001A1"],
    reasoning:
      "Use eukaryotic host organism (e.g., S. cerevisiae or Y. lipolytica) instead of prokaryotic E. coli to avoid element 1.",
    estimated_timeline: "2-4 months",
  },
  {
    action_type: "design_around",
    priority: "critical",
    description:
      "Implement design-around for US0000000002A1 — 1 option(s) identified.",
    patent_ids: ["US0000000002A1"],
    reasoning:
      "Use reactive extraction with tri-n-octylamine (TOA) instead of cooling crystallization.",
    estimated_timeline: "2-4 months",
  },
  {
    action_type: "challenge_ipr",
    priority: "high",
    description:
      "Evaluate inter partes review for US0000000001A1 (moderate invalidity argument).",
    patent_ids: ["US0000000001A1"],
    reasoning:
      "A combined obviousness argument under 35 U.S.C. §103 using Fictional Alpha and Fictional Beta has moderate strength.",
    estimated_timeline: "3-6 months for IPR petition",
  },
  {
    action_type: "challenge_ipr",
    priority: "high",
    description:
      "Evaluate inter partes review for US0000000002A1 (moderate-strong invalidity argument).",
    patent_ids: ["US0000000002A1"],
    reasoning:
      "An anticipation argument based on Fictional Gamma is moderately strong — the reference discloses the core process.",
    estimated_timeline: "3-6 months for IPR petition",
  },
  {
    action_type: "accept_risk",
    priority: "medium",
    description:
      "Assess risk tolerance for US0000000003A1 (Fictional Nova). Medium risk with no clear mitigation path.",
    patent_ids: ["US0000000003A1"],
    reasoning:
      "Different production route (enzymatic vs. fermentation) but interpretive ambiguity on fumarate intermediate.",
    estimated_timeline: "",
  },
];

// ── Full FTO report ─────────────────────────────────────────────────────

export const TEST_REPORT: FTOReport = {
  report_id: "rpt_demo_succinic_001",
  generated_at: "2026-03-08T14:22:13.100Z",
  praviar_pipeline_version: "0.9.4",
  compound: SUCCINIC_ACID,
  risk_summary: RISK_SUMMARY,
  patent_analyses: PATENT_ANALYSES,
  doe_assessments: DOE_ASSESSMENTS,
  invalidity_assessments: INVALIDITY_ASSESSMENTS,
  verification: VERIFICATION,
  analysis_failures: ANALYSIS_FAILURES,
  data_limitations: DATA_LIMITATIONS,
  total_patents_found: 2417,
  patents_after_triage: 47,
  search_sources_used: [
    "pubchem_sdq",
    "surechembl",
    "bigquery",
    "bigquery_annotations",
    "patcid",
  ],
  source_health: SOURCE_HEALTH,
  scholarly_prior_art_count: 14,
  audit_trail: AUDIT_TRAIL,
  patent_narratives: PATENT_NARRATIVES,
  disclaimer:
    "SYNTHETIC COMPONENT-TEST FIXTURE: every organization, person, publication identifier, legal record, citation, and conclusion is fictional. This is not the canonical showcase and is not release evidence. It does not constitute legal advice, and it must not be used for a real matter.",
  llm_models_used: {
    triage: "claude-sonnet-4-20250514",
    analysis: "claude-sonnet-4-20250514",
    doe: "claude-sonnet-4-20250514",
    invalidity: "claude-sonnet-4-20250514",
    report: "claude-sonnet-4-20250514",
  },
  total_input_tokens: 126146,
  total_output_tokens: 31563,
  estimated_cost_usd: 4.82,
  step_token_usage: STEP_TOKEN_USAGE,
  action_items: ACTION_ITEMS,
  drawing_analyses: [
    {
      patent_id: "US0000000018A1",
      pages_fetched: 4,
      structures: [
        {
          patent_id: "US0000000018A1",
          page_number: 20,
          structure_index: 0,
          canonical_smiles: "CC(=O)Oc1ccccc1C(=O)O",
          confidence: 0.92,
          extraction_tool: "ensemble:cascade",
          is_markush: false,
        },
        {
          patent_id: "US0000000018A1",
          page_number: 20,
          structure_index: 1,
          canonical_smiles: "Cc1ccc(C(=O)Nc2ccccc2)cc1",
          confidence: 0.71,
          extraction_tool: "ensemble:majority_3_of_5",
          is_markush: false,
        },
      ],
    },
    {
      patent_id: "US0000000019A1",
      pages_fetched: 1,
      structures: [
        {
          patent_id: "US0000000019A1",
          page_number: 6,
          structure_index: 0,
          canonical_smiles: "",
          markush_cxsmiles: "[*:1]Cc1ccc(C(=O)N[*:2])cc1",
          markush_r_groups: ["R1: alkyl", "R2: aryl"],
          confidence: 0.88,
          extraction_tool: "markushgrapher",
          is_markush: true,
        },
      ],
    },
  ],
};
