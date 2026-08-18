# A04 — Evidence pipeline

```mermaid
flowchart TD
    I["Authorized compound + product/process scope"] --> S1["1. Resolve identity and query context"]
    S1 --> S2["2. Search, normalize, rank, family grouping"]
    S2 --> G1{"source health and minimum evidence?"}
    G1 -->|"no"| F1["fail / abstain with reason"]
    G1 -->|"yes"| S3["3. Structured triage"]
    S3 --> S4["4. Claim analysis"]
    S4 --> E{"risk, uncertainty, dense set, drawings, or weak evidence?"}
    E -->|"yes"| A["internal agentic escalation"]
    E -->|"no"| S5["5. Equivalents issue screening"]
    A --> S5
    S5 --> S6["6. Invalidity-material screening"]
    S6 --> S7["7. Deterministic verification"]
    S7 --> G2{"verification passes?"}
    G2 -->|"no"| F2["record blocking verification gaps"]
    G2 -->|"yes"| S8["8. Build report + provenance"]
    F2 --> S8
    S8 --> H["qualified human review"]
    H --> O["review record and governed artefact"]

    classDef guard fill:#fff7ed,stroke:#c2410c,color:#7c2d12;
    class G1,G2,E guard;
```

OCR/OCSR, structure similarity, retrieval scores, and model output are evidence inputs—not claim construction or a legal conclusion. Markush interpretation remains a material experimental limitation.

Failed deterministic checks remain visible in the report and downstream evidence directives, but block a positive clearance output until resolved; they do not disappear merely because a report artefact can still be assembled.
