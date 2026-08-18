# A06 — Core data model

This is the review-critical subset, not every operational table. The ORM remains authoritative.

```mermaid
erDiagram
    ORGANIZATION ||--o{ USER : contains
    ORGANIZATION ||--o{ ANALYSIS : owns
    USER o|--o{ ANALYSIS : initiates
    ANALYSIS ||--o{ PIPELINE_EVENT : emits
    ANALYSIS ||--o{ REVIEWER_DECISION : receives
    ANALYSIS ||--o| ANALYSIS_REVIEW_STATUS : summarizes
    ANALYSIS ||--o{ COMMENT : discusses
    ANALYSIS ||--o{ EXPORT_JOB : generates
    ANALYSIS ||--o{ EXTERNAL_REPORT_GRANT : shares
    COMPOUND ||--o{ ORGANIZATION_COMPOUND : catalogued_as
    ORGANIZATION ||--o{ ORGANIZATION_COMPOUND : scopes

    ORGANIZATION {
      uuid id PK
      string name
      json settings
    }
    USER {
      uuid id PK
      uuid org_id FK
      string role
    }
    ANALYSIS {
      uuid id PK
      uuid org_id FK
      uuid initiated_by FK
      string status
      json report_data
    }
    PIPELINE_EVENT {
      uuid id PK
      uuid analysis_id FK
      int step_number
      json payload
    }
    REVIEWER_DECISION {
      uuid id PK
      uuid analysis_id FK
      string decision
    }
    ANALYSIS_REVIEW_STATUS {
      uuid id PK
      uuid analysis_id FK
      string status
    }
    EXPORT_JOB {
      uuid id PK
      uuid analysis_id FK
      string status
      string artifact_sha256
    }
```

Tenant isolation applies to tenant-owned records even when a foreign key already points to an analysis. Relationships and columns change more frequently than this overview; consult `api/src/api/db/models_*.py` and migrations before implementing against the schema.
