# Stage 8 frozen-payload formal retrieval summary

The formal dataset contains 280 rows: 260 answerable rows are scored and 20
reviewed abstention rows remain visible but are excluded from ranking and routing
denominators. All three runs use the same frozen dataset, Stage 4 provenance
snapshot, and verified runtime payload artifact. The runtime payload manifest
binds its compressed file SHA-256, each collection payload SHA-256, collection
name, chunk count, and the snapshot SHA-256.

| Mode | Scored | Excluded abstentions | Execution errors | Recall@5 | MRR@5 | NDCG@5 |
|---|---:|---:|---:|---:|---:|---:|
| BM25 | 260 | 20 | 0 | 0.5235 | 0.5206 | 0.4737 |
| Vector | 260 | 20 | 0 | 0.6237 | 0.6311 | 0.5798 |
| RRF | 260 | 20 | 0 | 0.5428 | 0.5440 | 0.4889 |

Automatic routing is independent of the retrieval mode: single-law Top-1
accuracy is 0.8182 and candidate recall is 0.8019, with zero execution errors.

Primary reports:

- `stage8_formal_bm25_runtime_payload_20261028.json`
- `stage8_formal_vector_runtime_payload_20261028.json`
- `stage8_formal_rrf_runtime_payload_20261028.json`

The earlier reports that query a reopened persistent Chroma HNSW directory are
retained only as diagnostics. They are not release evidence because the Windows
persistent index failed after a process restart. These reports instead use the
process-local mirror reconstructed from
`data/evaluation/stage8/stage8_runtime_payload_20261028.json.gz`.
