# Security Policy

## Supported Code

Security fixes may be applied to the current default branch when maintenance
capacity permits. Historical commits, forks, deployments, local branches, and
downloaded snapshots are unsupported.

## Reporting A Vulnerability

Do not open a public issue for a suspected vulnerability or include customer
data, credentials, exploit payloads, or tenant identifiers in a public channel.
Use the repository's private GitHub security-advisory flow so maintainers can
coordinate triage and disclosure without exposing the report.

A useful report includes:

- the affected component and revision;
- reproduction steps that avoid real customer data;
- the expected and observed security boundary;
- likely impact, including whether tenant isolation, authentication, report
  integrity, billing, or availability is affected; and
- a safe proof of concept, if one is necessary to reproduce the issue.

Do not access another tenant, persist access, exfiltrate data, degrade service,
send unsolicited messages, or test a production system without written
authorization.

## Triage objectives

This best-effort project has no guaranteed acknowledgement or remediation
deadline. When maintenance capacity permits, triage aims to:

- assign an owner and provisional severity before requesting additional
  reproduction detail;
- preserve relevant evidence and rotate exposed credentials immediately;
- use the incident-response path for suspected cross-tenant exposure, active
  compromise, destructive impact, or material report-integrity failure; and
- coordinate disclosure only after affected users and systems are protected.

These best-effort triage objectives are not contractual response or remediation
service levels.

## Archive boundary

A repository test, template, scanner configuration, or policy is not evidence
that a deployment has passed penetration testing or external assurance. This
archive receives best-effort maintenance and must not be used for confidential
matters without an independent security and privacy assessment. See
`MAINTENANCE.md` and `SUPPORT.md`.
