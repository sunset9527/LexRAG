# Stage 8 answer-review sampling design

The Stage 8 answer-quality review receives exactly 100 frozen question IDs.  It
includes every one of the 20 `should_abstain` rows, because incorrect refusal
behaviour is high risk and cannot be inferred from retrieval metrics.  The
remaining 80 slots are sampled deterministically from the 260 answerable rows.

The answerable allocation is proportional by question type, with largest-
remainder rounding: baseline direct lookup 31, oral without law name 15,
adjacent/confusable 12, cross-law 12, and multi-hop 10.  Within every question
type, the sampler first distributes across difficulty and expected knowledge
bases where capacity permits, then chooses stable pseudo-random rows using a
published seed.  Output records copy only frozen evidence/expected-answer
facts and add blank human-review fields; they never change labels or count as
reviewed answers.

The sampler emits both JSONL review records and a manifest binding dataset
bytes, selected IDs, seed, allocations and source commit.  Later real workflow
outputs and human decisions are joined by `id`.
