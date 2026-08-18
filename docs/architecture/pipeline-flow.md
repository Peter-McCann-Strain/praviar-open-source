# Pipeline flow

Use the two canonical architecture views:

- [A03 — Analysis sequence](src/03-analysis-sequence.md) for API, dispatch, progress, persistence, review, and export.
- [A04 — Evidence pipeline](src/04-evidence-pipeline.md) for the eight analysis stages, internal escalation, verification, abstention, and human review.
- [A09 — Runtime phase map](src/09-runtime-phase-map.md) for the exact implemented phase order, enrichment branches, checkpoints, and final evidence gates.
- [A10 — Vision extraction and evidence fusion](src/10-vision-evidence-fusion.md) for drawing acquisition, segmentation, OCSR fusion, live hard-failure versus per-item abstention paths, analysis/report use, and the separate non-vision clearance substrate.

The hosted production reference dispatches analysis work through Cloud Tasks to an OIDC-authenticated launcher, which starts a separate Cloud Run Job. Local development uses the explicit local dispatcher documented in the runtime configuration.

The detailed implementation reference is [`docs/PIPELINE.md`](../PIPELINE.md).

Praviar has one adaptive runtime profile. Escalation is internal and recorded as metadata rather than presented as a user-selectable accuracy mode. Checkpoints are saved after completed stages; failures must remain visible, and resume must continue from the last valid checkpoint.

Timings depend on source availability, provider limits, candidate volume, configured evidence gates, and model access. This architecture document intentionally publishes no duration or accuracy estimate.
