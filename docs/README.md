# Documentation

Praviar is an unsupported research archive. These documents explain the source
and its design; they do not certify a deployment, establish legal accuracy, or
provide operating assurance.

## Start here

| Document                                     | Use it for                                                                                |
| -------------------------------------------- | ----------------------------------------------------------------------------------------- |
| [Getting started](getting-started.md)        | Run the fictional interface without accounts, external services, or credentials           |
| [Known limitations](limitations.md)          | Understand the legal, data, model, security, deployment, and support boundaries           |
| [Pipeline reference](PIPELINE.md)            | Inspect the implemented stages, checkpoints, models, and data flow                        |
| [Architecture index](architecture/README.md) | Navigate the system, container, sequence, trust-boundary, data, runtime, and vision views |

## Component guides

| Area              | Guide                                                         |
| ----------------- | ------------------------------------------------------------- |
| Web interface     | [`web/README.md`](../web/README.md)                           |
| API and workers   | Source and tests under [`api/`](../api/)                      |
| Evidence pipeline | [`praviar_pipeline/README.md`](../praviar_pipeline/README.md) |
| Research tooling  | [`research/README.md`](../research/README.md)                 |
| Local engineering | [`development/README.md`](development/README.md)              |

## Reference designs

The following documents preserve engineering designs for study. They have not
been validated as deployment or operating instructions for an unknown
environment:

- [Deployment reference](deployment.md)
- [Operations reference](operations/README.md)
- [GCP Terraform reference](../infra/terraform/README.md)
- [Vercel reference](../web/VERCEL_SETUP.md)

Using those designs safely requires independent review of identity, network,
data residency, retention, secrets, costs, monitoring, backup, incident
response, third-party terms, and applicable law.

## Project policies

- [Contributing](../CONTRIBUTING.md)
- [Security reporting](../SECURITY.md)
- [Best-effort support](../SUPPORT.md)
- [Maintenance status](../MAINTENANCE.md)
- [Apache-2.0 licence](../LICENSE)
- [Third-party notices](../THIRD_PARTY_NOTICES.md)
