# Deployment reference

> [!WARNING]
> This is an unvalidated design note, not a supported deployment guide. The
> public archive has not been operated as a production service and offers no
> availability, security, backup, recovery, performance, or service-level
> assurance.

The only account-free path documented for this archive is the
[fictional local demo](getting-started.md). Running the API, pipeline, or a
hosted topology requires independent engineering and professional review.

## Local engineering shape

The source contains example configuration files for the three runtime
surfaces:

```bash
cp api/.env.example api/.env
cp praviar_pipeline/.env.example praviar_pipeline/.env
cp web/.env.local.example web/.env.local
```

Those copies are ignored by Git. They contain placeholders only; a downstream
operator must decide which external providers to use and obtain the necessary
accounts, credentials, licences, and data rights. Never enter confidential or
real legal matters into an unreviewed environment.

The root Compose file starts PostgreSQL and Redis for local engineering:

```bash
docker compose up --wait postgres redis
```

The API, worker, migrations, and pipeline are not part of the quick-start demo.
Their package READMEs and example settings expose development entry points, but
those entry points are not production operating instructions.

## Hosted topology shown in the source

Architecture diagrams and reusable Terraform modules illustrate a possible
topology using a Next.js frontend plus GCP services such as Cloud Run, Cloud
SQL, Memorystore, Cloud Tasks, Pub/Sub, object storage, Secret Manager, and
logging. Environment-specific Terraform compositions, deployment identities,
and deployment automation are not included in the public archive.

An organisation adapting that reference would need to design, implement, and
validate at least:

- identity, tenant isolation, network boundaries, and secrets management;
- regions, residency, retention, deletion, backup, restore, and disaster
  recovery;
- builds, migrations, staged rollout, monitoring, rollback, and incident
  response;
- database roles, row-level-security canaries, queue permissions, and provider
  egress;
- vulnerability management, penetration testing, dependency review, and
  supported-version policy;
- source, model, dataset, privacy, export-control, and professional-use rights;
- cost limits, staffing, support responsibilities, and acceptance tests.

The presence of code or a Terraform module does not establish that any of
those controls is deployed or effective.

## Where to read next

- [Known limitations](limitations.md)
- [Architecture index](architecture/README.md)
- [GCP Terraform reference](../infra/terraform/README.md)
- [Best-effort maintenance](../MAINTENANCE.md)
- [Security reporting](../SECURITY.md)
