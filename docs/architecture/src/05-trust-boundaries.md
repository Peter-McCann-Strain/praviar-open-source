# A05 — Trust boundaries

```mermaid
flowchart LR
    subgraph Client["Untrusted client boundary"]
        B["Browser"]
    end
    subgraph App["Application identity boundary"]
        A["API authorization"]
        Q["Cloud Tasks delivery"]
        L["OIDC-authenticated launcher"]
        J["fenced analysis Job"]
    end
    subgraph Tenant["Tenant data boundary"]
        D[("PostgreSQL / org_id / RLS")]
        O[("Private export objects")]
        E["Progress events and audit records"]
    end
    subgraph Secrets["Credential boundary"]
        SM["Environment / secret manager"]
    end
    subgraph External["External provider boundary"]
        X["Patent, chemistry, literature, and model APIs"]
    end

    B -->|"session / scoped request"| A
    A -->|"SET LOCAL tenant context"| D
    A --> E
    A -->|"durable task"| Q
    Q -->|"signed OIDC request"| L
    L -->|"reserve execution id"| D
    L -->|"launch with execution id"| J
    J --> D
    J --> O
    J --> E
    SM -.->|"runtime-only credentials"| A
    SM -.->|"runtime-only credentials"| L
    SM -.->|"runtime-only credentials"| J
    J -->|"bounded egress; data leaves control"| X
    D -->|"reviewable report"| A
    A -->|"policy-gated response"| B
```

Public examples must be fictional. A public demo must not accept confidential uploads. Hashes and signatures demonstrate integrity relative to recorded inputs; they do not establish source truth, legal sufficiency, or trustworthy model behavior.
