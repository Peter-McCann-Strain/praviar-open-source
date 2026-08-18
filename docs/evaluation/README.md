# Evaluation results

This page records the strongest measured results currently available for the
chemical-patent-analysis codebase. The corresponding machine-readable summary
is [`results.json`](results.json).

The measurements use real patent pages, real chemical drawings, and named
therapeutic compounds. The public archive publishes aggregate results and
source-artifact hashes, while excluding source images, model weights, raw
per-image predictions, and provider-derived corpora.

## Live patent-page to structure pipeline

The April 2026 US evaluation exercised the full visual path:

```text
real patent page
  -> MolDet region detection
  -> crop extraction
  -> MolClassifier routing
  -> five OCSR model predictions
  -> canonicalisation and ensemble fusion
  -> IoU association with labelled regions
  -> exact canonical-SMILES scoring
```

| Measure                                    |         Result |
| ------------------------------------------ | -------------: |
| US patent pages                            |            128 |
| Annotated drawing regions                  |          1,069 |
| Detected/matched regions                   |          1,035 |
| Detection recall                           |         96.82% |
| Scalar-SMILES-labelled targets             |             86 |
| Exact structures end to end                | 62/86 (72.09%) |
| Resolved labelled structures               |             70 |
| Exact structures conditional on resolution | 62/70 (88.57%) |

The artifact identifies the run as `live`, jurisdiction `us`, detector
`moldet`, and IoU threshold `0.5`. Its SHA-256 is
`4172c13d6f46316a3314d28adc3e1c44307cb75cb9f16d516c7d9cbb36a0e8bf`.

## Live five-model OCSR ensemble

The March 2026 crop-level benchmark called MolScribe, MolSight, DECIMER,
MolNexTR, and MolGrapher for each image rather than replaying an inference
cache. Exact match means equality after RDKit canonicalisation.

| Measure                    |           Result |
| -------------------------- | ---------------: |
| USPTO patents              |               50 |
| Chemical-structure crops   |              447 |
| Fused valid structures     |   447/447 (100%) |
| Exact canonical structures | 410/447 (91.72%) |
| Elapsed time               | 20,034.5 seconds |

Source hashes:

- Results: `641d10c8df988edae72844bb93319efa4d8ba02a98cc0ce9f63db286c1069476`
- Summary: `9475d1f0ec195aa0edcbb38ad5d14e029e306055dca339e7e8059d4735b82bbb`

### Does the ensemble add value?

On 76 crops from the live 128-page run where all five model predictions were
available:

| Configuration                    |          Exact |
| -------------------------------- | -------------: |
| Full ensemble                    | 62/76 (81.58%) |
| Best individual voter, MolScribe | 59/76 (77.63%) |
| MolSight                         | 58/76 (76.32%) |
| DECIMER                          | 54/76 (71.05%) |
| MolNexTR                         | 53/76 (69.74%) |
| MolGrapher                       | 37/76 (48.68%) |

The ensemble therefore improved on the best individual voter by 3.95
percentage points on this fully comparable subset. The ablation artifact hash
is `e244198a18d1828d1f9c9a85726733425cd560a7c9b2b08d5253687f3e953e66`.

## Multi-jurisdiction OCSR

The separate live PatCID evaluation covered CN, EU, JP, KR, and US material.

| Jurisdiction | Exact / rows | Exact rate |
| ------------ | -----------: | ---------: |
| CN           |        41/47 |     87.23% |
| EU           |        36/60 |     60.00% |
| JP           |        44/73 |     60.27% |
| KR           |        30/39 |     76.92% |
| US           |      103/139 |     74.10% |
| **Overall**  |  **254/358** | **70.95%** |

There are 355 unique image identifiers in the 358 scored rows; three images
appear in two dataset partitions. Results hash:
`0f51f63e32f535c800055b4496d5ff5e6a0fc22a56ea53f0718cf516732640c8`.

## Patent-drawing detection

The detector-only evaluation used 50 real US patent pages with 393 annotated
regions and IoU threshold 0.5:

- 380 true positives, 20 false positives, and 13 false negatives;
- 95.0% precision;
- 96.69% recall;
- 95.84% F1; and
- 0.810 mean IoU for matched regions.

Artifact hash:
`c6f431fe60e837ea8d47fd7653e217cccf31b0b3f7982e32122745f5ab29c32c`.

## Broad cached cross-dataset re-score

A later deterministic re-score applied one exact-match policy to 12,560 cached
model-output rows. It did **not** rerun inference.

| Dataset     |    Exact / images | Exact rate |
| ----------- | ----------------: | ---------: |
| USPTO       |       5,360/5,633 |     95.15% |
| CLEF        |           800/905 |     88.40% |
| UOB         |       5,040/5,740 |     87.80% |
| ACS         |           216/282 |     76.60% |
| **Overall** | **11,416/12,560** | **90.89%** |

The 18.55-point USPTO-to-ACS spread is useful evidence of domain shift; the
aggregate should never be reported without the per-dataset values. Artifact
hash: `e4bccc50a99c909a71c31aacafa4d3077d5f8859c9ee66ceb95422a6215a0cfa`.

## Real-compound pipeline evidence

### Provider-backed retrieval sweep

A batch search covered 50 named therapeutics across small molecules and
biologics. Forty-nine completed and one provider request failed. The completed
runs returned 17,584 deduplicated/ranked Step 2 patent hits, with a mean of
351.7 hits per requested compound. This measures retrieval execution, not
relevant-family recall or legal correctness. Summary hash:
`a7ea123d1dc44e870b02526e8f23e86a98908998a66263f59c707f67b3a262c8`.

Stored research runs also exercise report generation on real named compounds,
including atorvastatin and osimertinib. They are workflow artifacts, not legal
opinions or independently adjudicated correctness evidence.

## What these results establish

They establish that:

- the detector, classifier, OCSR workers, fusion, normalisation, and evaluation
  code have run on real patent material;
- the five-model ensemble can outperform each individual voter on a common
  eligible subset;
- the system records failures and domain differences rather than presenting a
  single context-free accuracy number; and
- the retrieval and analysis workflows have been exercised on real compound
  names and patent records.

They do not establish that:

- a generated report is a legal opinion;
- patent search is complete;
- the evaluation crops are independent by patent family;
- model training overlap has been excluded;
- the exact March/April model checkpoints are cryptographically bound into
  every artifact; or
- the software has a production SLA or independently measured legal accuracy.

MolDet is subject to a non-commercial licence and MolNexTR provenance remains
unresolved. No model weights are distributed here. See
[Model licences](../../MODEL_LICENSES.md), the
[vision architecture](../architecture/src/10-vision-evidence-fusion.md), and
the [pipeline documentation](../PIPELINE.md).
