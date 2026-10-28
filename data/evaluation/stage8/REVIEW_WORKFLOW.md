# Stage 8 review workflow

Stage 8 started with a 300-row candidate review queue: 100 existing legacy seed
rows plus 200 newly proposed hard candidates. After the documented scope
decision, 280 approved rows remain in the reviewed candidate baseline. Neither
the queue nor that baseline is a frozen or formal evaluation dataset.

For each row, a human reviewer checks the question, proposed question type and
difficulty, knowledge-base scope, relevant article IDs, abstention decision, and
local source locator. The reviewer records their name, timestamp, and review
note, then materializes a separately verified/approved row.

Formal materialization joins the read-only reviewed baseline to an immutable
Stage 4 provenance snapshot. Each formal row contains a `source_evidence` list
with exactly one evidence object per expected knowledge-base slug; article IDs
must form an exact, duplicate-free partition across those objects. The
materializer must fail if a label matches zero or multiple source catalogs.

Only separately materialized approved rows that pass the formal validator may
become the frozen Stage 8 dataset. This freezes legal-label provenance only.
Candidate/baseline rows and provenance freezing must not be presented as
retrieval or answer-quality metrics.

The 2026-10-27 freeze completed this process as
`stage8_frozen_280.jsonl`, bound to `stage4_provenance_2026-10-27.json`
by `stage8_frozen_280.manifest.json`. Committed artifact-integrity tests enforce
the row/evidence/label distributions, eight live version identities, and all
three byte-level input/output hashes.
