# Stage 8 isolated vector-index repair design

## Purpose

Restore queryable HNSW segments for the Stage 8 formal Vector and RRF evaluation
without changing the original Chroma directory, the frozen 280-row dataset, or
any legal-source record.

## Chosen approach

The repair creates a *new* evaluation-only Chroma directory.  For each of the
eight collections bound by the frozen Stage 4 snapshot, it reads the existing
IDs, documents, metadata, and stored embedding vectors from the current
evaluation copy, then recreates that collection with the same name and metadata
and inserts the same payload in bounded batches.  Chroma consequently writes new
HNSW segment files without re-embedding source text or contacting a model
provider.

This is preferred over changing the original index or rerunning only failed
queries: the original remains evidence, and rebuilding all snapshot collections
removes hidden segment-reader failures from the candidate being measured.

## Boundaries and validation

- The source and target must be different existing/new directories; the source
  is opened only for reads.
- Before export, each collection must match the frozen snapshot's name, count,
  collection identity metadata, and per-chunk source/version/article provenance.
- The tool rejects malformed, duplicate, missing, or non-aligned IDs/documents/
  metadata/embeddings.
- After import, it verifies the target payload and provenance match the exported
  payload, then performs a minimal vector query against every collection.  A
  missing HNSW reader is a failure, not a skipped collection.
- The repair report records source/target paths, collection names, counts,
  payload digests, and queryability outcomes.  It makes no legal-quality claim.

## Follow-up

Only a fully validated repaired copy can be supplied to the existing frozen
Stage 8 formal CLI for new Vector and RRF reports.  Those reports will state the
repaired directory and remain separate from the failed diagnostic runs.
