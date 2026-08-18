# Known limitations

This is the canonical limitation statement for the open-source chemical patent
analysis system. It applies even when a code path, adapter, test, diagram, or
reference configuration appears complete.

## Legal and professional boundary

- The software does not provide legal advice, a freedom-to-operate opinion, claim
  construction, or a guarantee of non-infringement.
- Evidence retrieval and structured reports do not establish clearance,
  validity, enforceability, expiry, safe-harbour availability, or an appropriate
  legal conclusion.
- Qualified counsel must define the matter scope and review the underlying
  claims, prosecution history, legal status, jurisdictions, dates, products,
  processes, and intended uses.

## Search and source coverage

- No search strategy proves completeness. Unpublished applications cannot be
  searched, and publication, translation, family, legal-status, and provider
  delays can change the available record.
- Public-source adapters are not substitutes for specialist commercial patent
  databases. An adapter's presence does not include upstream access, a licence,
  current data, or guaranteed availability.
- Retrieval, ranking, family grouping, and name/structure normalisation can
  produce false positives, false negatives, or incomplete groupings.

## Chemistry, claims, and computer vision

- Name, CAS, SMILES, InChI, salt, stereochemistry, tautomer, formulation,
  process, and use context can resolve incorrectly or ambiguously.
- Molecular similarity and substructure matches are research signals, not claim
  scope.
- Markush interpretation and optical chemical-structure recognition are
  experimental. Model-derived drawing evidence may be unavailable, withheld,
  or wrong.
- Model weights are not included. Each external model, dataset, patent source,
  and API has its own rights and operating conditions.

## Evaluation

- The fictional demo shows interface states, not a live compound-to-report
  analysis and not a correct patent-status assertion.
- Software tests cover behaviour and contracts; they do not measure legal
  accuracy, search completeness, false-clear performance, reviewer quality, or
  real-world utility.
- The published engineering evaluations are not an independently
  counsel-adjudicated measure of legal accuracy, search completeness,
  false-clear rate, or report reliability. See
  [Evaluation results](evaluation/README.md) for the measured computer-vision,
  retrieval, and recorded prompt-protocol results that are available.

## Security, privacy, and tenancy

- Repository controls and tests are not a penetration test, privacy assessment,
  compliance certification, or proof of secure operation.
- Do not use confidential, privileged, personal, regulated, or customer data in
  the synthetic demo or an unreviewed deployment.
- A deployer must independently review authentication, authorisation, tenant
  isolation, encryption, logging, retention, deletion, egress, backup, restore,
  incident response, secrets, and provider contracts.

## Deployment and integrations

- Infrastructure, operations, identity, storage, queue, and cloud documents are
  unvalidated reference designs. No hosted service is provided.
- There is no production guarantee, supported connector catalogue, generic
  connector SDK, SCIM, buyer-VPC, on-premises, air-gapped, CMEK, or BYOK offer.
- Example integrations may require material engineering, schema mapping,
  licences, security review, and acceptance testing before use.

## Reproducibility and maintenance

- External providers, closed models, web sources, and legal-status records can
  change independently of the source archive.
- Optional dependencies and external credentials are not bundled. Provider
  calls may cost money and disclose inputs to third parties.
- Maintenance is best effort. No uptime, response time, remediation deadline,
  supported-version window, service level, warranty, or legal support is
  offered.

For the implemented flow, read [the pipeline reference](PIPELINE.md). For
service and trust boundaries, read [the architecture index](architecture/README.md).
