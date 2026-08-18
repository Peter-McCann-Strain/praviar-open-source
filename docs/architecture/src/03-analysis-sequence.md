# A03 — Analysis sequence

```mermaid
sequenceDiagram
    actor U as Researcher
    participant W as Web
    participant A as API
    participant D as PostgreSQL
    participant Q as Cloud Tasks
    participant L as Worker launcher
    participant J as Analysis Job / pipeline
    participant R as Redis
    actor C as Reviewer

    U->>W: submit authorized matter and product scope
    W->>A: POST /analyses
    A->>D: create tenant-owned analysis
    A->>Q: enqueue durable task
    A-->>W: analysis id + pending status
    W->>A: subscribe to analysis SSE
    A->>D: replay persisted events
    A->>R: subscribe to live channel
    Q->>L: OIDC-authenticated launch request
    L->>D: reserve or reuse execution fence
    L->>J: start Cloud Run Job with execution id
    L-->>Q: durable launch accepted
    J->>D: claim tenant-scoped execution lease
    loop eight pipeline stages
        J->>D: persist progress event
        J->>R: publish progress
        R-->>A: progress event
        A-->>W: SSE frame
    end
    J->>D: persist report or explicit failure
    A-->>W: completed or failed state
    W-->>C: evidence-bearing review workspace
    C->>A: record reviewer decision
    A->>D: persist decision + audit event
    C->>A: request governed export/share
    A-->>C: artefact or blocking findings
```

The synthetic demo replays fixtures in the web application and does not execute this queue, launcher, Job, provider, or persistence sequence.

Pipeline resume checkpoints are signed files in configured runtime storage; they are not represented as PostgreSQL rows in this view. Human checkpoint decisions and progress events are persisted separately by the API.
