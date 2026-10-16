# Evaluation report status

The JSON files in this directory preserve a provisional engineering snapshot. They are versioned for traceability, not as formal evidence of legal-answer quality.

## Why the snapshot is provisional

- The input `data/evaluation/eight_law_evaluation_100.jsonl` contains 85 rows that were promoted from `pending` to `approved` by supplying one shared review date.
- Those rows do not have per-item human-review evidence, and their source text still says that review is pending.
- The workflow report has `reviewed_count=0` and `assertion_support_rate=null`.
- The report metadata does not contain a complete run date, code commit, legal-source manifest, embedding version, chunker version, and collection hash.

Consequently, these files must not be cited as formal README, resume, release, or legal-quality metrics. Stage 8 will rebuild the frozen dataset and rerun all evaluations from one frozen commit after per-item review is complete.

## Preserved files

| File | SHA-256 | Status |
|---|---|---|
| `eight_law_100_bm25_top5.json` | `8A3FCC0FDCA2D5AB0789C6BA53053AD50645CBCBBB449FD159460DF922C724EC` | Provisional retrieval snapshot |
| `eight_law_100_vector_top5.json` | `B1C05942320F701771D3FAB519C5487F619EFD1A534AFF8A0372AB993052A85B` | Provisional retrieval snapshot |
| `eight_law_100_rrf_top5.json` | `363ED1AD61D43FF4A4C576F28CE749B49180D47FDE24DB9A7D1E6CABCDAF3288` | Provisional retrieval snapshot |
| `eight_law_100_workflow.json` | `F09EC25C0FC4793F195028879E385862C6FAE863DCCACAF9A5DE5C0DFBBE5038` | Provisional workflow snapshot; no assertion-support review |
