# Data model

The canonical architecture-level entity diagram is [A06 — Core data model](src/06-core-data-model.md).

That view intentionally covers only the review-critical lifecycle. It is not a complete database specification. SQLAlchemy models under `api/src/api/db/models_*.py` and Alembic migrations are authoritative for columns, constraints, row-level security, and operational tables.

When changing a core relationship:

1. update the ORM and migration;
2. verify tenant-scoping and real-PostgreSQL/RLS tests;
3. regenerate affected API/shared contracts; and
4. update A06 in the same change.
