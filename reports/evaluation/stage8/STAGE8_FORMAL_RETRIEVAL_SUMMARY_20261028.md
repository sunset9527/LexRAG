# Stage 8 formal retrieval summary

Frozen dataset: 280 rows total; 260 answerable rows scored and 20 abstention
rows retained but excluded from retrieval/routing denominators.  All reports
below bind to Git commit `0cb2f81b51cad4998a5a5037be8145657f8466f8`, the
frozen 280-row manifest, and the Stage 4 provenance snapshot.

| Mode | Scored | Execution errors | Recall@5 | MRR@5 | NDCG@5 |
|---|---:|---:|---:|---:|---:|
| BM25 | 260 | 0 | 0.5235 | 0.5206 | 0.4737 |
| Vector | 260 | 0 | 0.6237 | 0.6311 | 0.5798 |
| RRF | 260 | 0 | 0.6319 | 0.6326 | 0.5762 |

Automatic routing, reported separately from oracle retrieval, is unchanged by
retrieval mode: single-law Top-1 accuracy is 0.8182 and candidate recall is
0.8019.

The formal Vector/RRF candidate is the isolated directory
`data/chroma_stage8_eval_repaired_20261028_v2`.  It was reconstructed from the
verified stored IDs, texts, metadata and embeddings after the copied legacy
HNSW segments failed to load.  The source index, frozen legal dataset, and
source provenance snapshot were not modified.  Each reconstructed collection
was checked for payload equality, provenance, chunk count and a real vector
query before use.

Primary reports:

- `stage8_formal_bm25_20261028_final.json`
- `stage8_formal_vector_repaired_20261028_final.json`
- `stage8_formal_rrf_repaired_20261028_final.json`
