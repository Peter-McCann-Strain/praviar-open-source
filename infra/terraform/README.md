# GCP infrastructure reference

The Terraform source in this archive is an unvalidated reference design. It is
included to make the intended service boundaries inspectable; it is not a
supported deployment recipe and has not been independently validated for an
unknown organisation, account, region, or threat model.

The archive retains reusable module designs for networking, data stores,
runtime services, queues, object storage, identity, logging, and monitoring.
Environment-specific compositions and automation identities are deliberately
not part of the public archive.

## What must be decided before use

A downstream operator must independently define and review:

- project and billing ownership;
- identity federation and least-privilege deployment roles;
- regions, residency, retention, backup, restore, and disaster recovery;
- database, queue, storage, and network topology;
- secret creation, rotation, access logging, and incident response;
- provider versions, lockfiles, plans, cost limits, and change approval;
- privacy, security, data-rights, and regulatory obligations.

Saved plans, state, variable files, credentials, and service-account keys can
contain sensitive values. They are not included and must never be committed.
Prefer short-lived identity federation over downloadable credentials, keep
secret values outside Terraform variables, and inspect every provider and role
change before use.

## Reference modules

The `modules/` directory illustrates these intended boundaries:

- project and API enablement;
- VPC and serverless connectivity;
- Cloud Run services and jobs;
- Cloud SQL, Memorystore, Cloud Tasks, Pub/Sub, and object storage;
- Artifact Registry and Secret Manager bindings;
- load balancing, logging, and monitoring.

Module presence is not evidence that a control is deployed, effective, secure,
complete, or suitable for production. Read
[Known limitations](../../docs/limitations.md) before adapting any part of this
reference.
