# A01 — System context

The system organizes evidence for a researcher or qualified reviewer. Source publishers and model providers remain independent systems with their own availability, terms, and accuracy limits.

```mermaid
flowchart LR
    R["Researcher"] -->|"defines a fictional or authorized matter"| P["Praviar research preview"]
    C["Qualified counsel / reviewer"] -->|"reviews sources and records decisions"| P
    P -->|"queries under source terms"| PS["Patent and legal-status sources"]
    P -->|"resolves public chemistry identifiers"| CS["Chemistry sources"]
    P -->|"optional analysis requests"| MP["Model providers / local models"]
    P -->|"optional literature queries"| LS["Literature sources"]
    P -->|"review artefacts"| C

    classDef external fill:#f3f4f6,stroke:#6b7280,color:#111827;
    classDef system fill:#ccfbf1,stroke:#0f766e,color:#134e4a;
    class P system;
    class PS,CS,MP,LS external;
```

Out of scope: independently verified legal accuracy, unpublished applications, universal jurisdiction coverage, and any guarantee that retrieved evidence is complete or current.
