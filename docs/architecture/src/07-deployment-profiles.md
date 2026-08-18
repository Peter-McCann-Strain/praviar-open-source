# A07 — Deployment profiles

```mermaid
flowchart TB
    subgraph Local["Local synthetic showcase"]
        LB["Local browser"] --> LW["Next.js + explicit demo mode"]
        LW --> LF["repository-owned synthetic fixtures"]
        LN["No API, provider keys, model weights, or confidential uploads"]
    end

    subgraph Hosted["Hosted reference topology — not deployment evidence"]
        HB["Browser"] --> HW["Next.js"]
        HW --> HA["FastAPI service"]
        HA --> HD[("PostgreSQL + RLS")]
        HA <--> HR[("Redis")]
        HA --> HQ["Cloud Tasks"]
        HQ -->|"OIDC"| HL["internal worker launcher"]
        HL -->|"reserve execution fence"| HD
        HL -->|"Cloud Run v2 run"| HJ["analysis Job"]
        HJ --> HD
        HJ --> HR
        HJ --> HO[("private object storage")]
        HJ --> HX["approved external providers"]
        HS["secret manager / ADC"] -.-> HA
        HS -.-> HL
        HS -.-> HJ
    end
```

The local profile is the portfolio entry point. The hosted topology requires environment-specific IAM, data-protection, monitoring, backup, incident-response, penetration-testing, and release evidence that source code alone cannot supply.
