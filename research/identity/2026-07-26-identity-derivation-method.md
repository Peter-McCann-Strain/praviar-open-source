# Identity derivation method — evidence review (2026-07-26)

## Production decision

Praviar keeps the authoritative resolved compound unchanged. Tautomers and
possible activated/deprotected parents are fingerprint-bound **additional search
lanes** that require the mandatory identity-review attestation. They are not
synonyms, metabolites, or asserted active ingredients.

### Tautomers

- Use RDKit `MolStandardize.TautomerEnumerator` with the shipped default rules,
  explicit `maxTautomers=32`, `maxTransforms=64`, and at most eight alternate
  search candidates.
- Record RDKit version, tautomer score version, status, bounds, enumeration
  count, selected canonical tautomer, every candidate ID, and integrity receipt.
- Expand search only when status is `Completed`. `MaxTautomersReached`,
  `MaxTransformsReached`, parsing failure, or enumeration failure is fail-closed.
- Require sanitization, one connected fragment, identical formula, exact mass,
  heavy-atom count, formal charge, and isotope inventory, with no radicals.
- RDKit documentation: [TautomerEnumerator API and bounded-result statuses](https://www.rdkit.org/docs/source/rdkit.Chem.MolStandardize.rdMolStandardize.html).

This is deterministic computational coverage, not proof of every pH-, solvent-,
assay-, or solid-state-relevant tautomer.

### Prodrug-parent hypotheses

Only bounded one-step cleavage hypotheses are generated:

1. carboxylic ester hydrolysis, considering both acid-side and
   alcohol/phenol-side products;
2. simple O-phosphate monoester dephosphorylation;
3. O- or N-carbamate deprotection only when one retained structure is dominant.

A candidate must sanitize, be connected and radical-free, introduce no new
heavy element, contain no dummy atom, have fewer heavy atoms and lower exact
mass than its source, retain at least 60% of source heavy atoms, and preserve a
source/product substructure relationship. At most four candidates enter search.

The transform is recorded as Reaction SMARTS with the RDKit version and rule
version. Relevant method evidence:

- [RDKit Reaction SMARTS behavior](https://www.rdkit.org/docs/RDKit_Book.html#reaction-smarts)
- [Ester linkages and esterase-mediated prodrug activation](https://pmc.ncbi.nlm.nih.gov/articles/PMC3132824/)
- [Phosphomonoester conversion to the hydroxyl parent](https://pmc.ncbi.nlm.nih.gov/articles/PMC7445155/)
- [Carbamates may be active motifs, not merely prodrugs](https://pmc.ncbi.nlm.nih.gov/articles/PMC4393377/)

Phosphonates, phosphoramidates/ProTides, cyclic or multiply esterified
phosphorus promoieties, carbonates, thioesters, and acyloxyamides are explicitly
unsupported rather than guessed. Complex phosphorus activation can require
several mechanistically distinct steps:
[phosphate/phosphonate prodrug strategies](https://pmc.ncbi.nlm.nih.gov/articles/PMC4774048/)
and [multi-step ProTide activation](https://pmc.ncbi.nlm.nih.gov/articles/PMC7409933/).

### Biologics when Purple Book has no exact match

FDA describes GSRS/UNII as the system that uniquely identifies regulated
substances using ISO 11238; a UNII can exist at any lifecycle stage and therefore
does **not** establish approval:
[FDA GSRS overview](https://www.fda.gov/industry/fda-data-standards-advisory-board/fdas-global-substance-registration-system).

The production route uses the official openFDA
[UNII endpoint](https://open.fda.gov/apis/other/unii/) for one exact,
case-normalized substance-name/UNII match and then the official
[substance endpoint](https://open.fda.gov/apis/other/substance/) for one record
whose:

- UNII matches;
- substance class is `protein`;
- definition type is `PRIMARY`;
- definition level is `COMPLETE`;
- record name set contains the submitted exact name.

Zero, ambiguous, non-protein, non-primary, or incomplete matches return no
identity; when Purple Book also has no match, resolution stops before search.

Live read-only verification on 2026-07-26:

- exact `ADALIMUMAB` UNII lookup returned `FYS6T7F842`, with name-index
  `meta.last_updated=2026-07-25`;
- UNII-to-substance lookup returned GSRS UUID
  `49c070a0-3b9f-4617-86ad-d5551a84fbab`, class `protein`, definition
  `PRIMARY`/`COMPLETE`, record version `119`, and substance dataset
  `meta.last_updated=2025-09-19`.

The two update dates are retained independently; the newer name-index date must
not be misrepresented as the substance-record update date.

## Known limits retained in the reviewer packet

- Tautomer rules do not model experimental equilibria.
- Cleavage candidates do not prove in-vivo activation or pharmacological
  activity.
- GSRS proves a substance identity record, not product licensure, equivalence,
  sequence/glycoform completeness for a particular product, or approval.
- Unsupported prodrug mechanisms require a separately resolved parent/metabolite
  analysis when decision-critical.
