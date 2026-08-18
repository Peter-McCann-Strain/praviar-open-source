# A02 — Container view

The local synthetic profile needs only the web container. The other containers describe the full application and hosted reference. The worker service is a short control-plane launcher; the long-running pipeline executes in a separate analysis Job.

```mermaid
flowchart TB
    U["Browser"] -->|"HTTP(S)"| W["Next.js web"]
    W -->|"REST + SSE"| A["FastAPI API"]
    A -->|"tenant-scoped SQL"| DB[("PostgreSQL + RLS")]
    A <-->|"cache + live events"| R[("Redis")]
    A -->|"durable task"| Q["Cloud Tasks (reference)"]
    Q -->|"OIDC internal HTTP"| L["Worker launcher service"]
    L -->|"reserve execution fence"| DB
    L -->|"Cloud Run v2 run"| J["Analysis Job"]
    J --> P["Praviar pipeline library"]
    J --> DB
    J --> R
    J -->|"exports"| O[("Private object storage")]
    P --> X["External data/model providers"]

    subgraph Runtime["Praviar runtime"]
        W
        A
        L
        J
        P
    end
```

`Cloud Tasks`, Cloud Run Jobs, hosted object storage, and the deployment shape are reference integrations. Their source code does not prove a deployed service or operational SLA.
