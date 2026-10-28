# LexRAG Stage 8 final validation design

## Purpose

Stage 8 converts the engineering-closed v3.0 codebase into one auditable release candidate. It does not add product features, agents, model providers, or microservices. The release conclusion must be reproducible from a single commit, data snapshot, runtime configuration, and report set.

## Scope and sequencing

The implementation is organised as a release train: first close the explicit Stage 6 carry-overs, then establish governed evaluation data and a shared run manifest, then execute retrieval, workflow, human-review, performance, security, browser, Docker, and release gates on the frozen candidate. A defect creates a new candidate and invalidates the affected downstream evidence; reports from different candidates are never combined.

## Data and evaluation contract

The existing 100-row eight-law file is provisional because 85 rows claim `approved` status while their source records still say pending review. Stage 8 preserves the historical files, restores those rows to an auditable review workflow, and publishes a 280-row formal statute retrieval dataset. Twenty version-sensitive candidates are retired rather than guessed against incomplete version rules; they are not part of the 280-row denominator. Each formal row records question, type, difficulty, expected knowledge bases, relevant articles, abstention expectation, per-knowledge-base source URL/version/hash/location, reviewer, date, and review note. The formal set contains 260 answerable rows and 20 fact-insufficient/abstention rows. Development samples may inform fixes; frozen test labels cannot be altered to fit system output.

Every evaluator emits the same per-item schema with retrieval contexts, response, citations, workflow trace, token usage, latency, run identity, and explicit execution errors. A run manifest binds those results to Git SHA, legal-source hashes, embedding and chunking versions, collection identifiers, model configuration, and dependency versions.

### Formal retrieval and routing runner

The legacy eight-law runner remains an engineering-regression tool and is not rewritten. A separate Stage 8 runner consumes only `stage8_frozen_280.jsonl` through the strict formal loader. It evaluates the 260 answerable rows with composite evidence identities `(knowledge_base_slug, article_id)`, so a same-numbered article from another law cannot count as a hit. For each row it records top-K ranked evidence per selected law, exact expected labels, first relevant rank, execution error (if any), and whether the result is included in the metric denominator.

Oracle retrieval and automatic routing are reported separately. Oracle retrieval sends each expected law to its verified collection and reports Recall@1/3/5, MRR@5 and NDCG@5 overall and by law, type and difficulty; a cross-law row receives one top-K list per expected law and is scored against the complete composite-label set. Automatic routing invokes the existing `KnowledgeBaseRouter` with the released catalogue and reports single-law Top-1 accuracy, candidate recall, and cross-law candidate recall. It must not pretend that an oracle-retrieval result measures routing quality.

The 20 abstention rows are retained in every run record but excluded from positive-label ranking and route-accuracy denominators because retrieval alone has no authoritative abstention decision. Their abstention accuracy is measured later from full-workflow outputs in the human-answer evaluation, not fabricated from an empty retrieval list. Reports expose these denominator decisions, skipped rows, and execution errors explicitly.

## Verification design

Retrieval comparisons run paired configurations on the frozen dataset: BM25, vector, RRF, rewrite, graph expansion, optional reranker, and the complete workflow. Reporting includes ranking, routing, abstention, contamination, latency, and paired uncertainty/statistical tests. Reranking remains disabled unless the frozen evaluation shows a reproducible quality benefit that justifies its resource cost.

One hundred stratified full-workflow answers receive evidence-located human review for legal correctness, support, citation fidelity, completeness, abstention, and severe error. Ragas and a fixed Judge configuration are diagnostic only and are calibrated against that human subset; neither replaces legal review. A solo-review fallback is interval re-review with explicitly limited claims; two blinded reviewers are used only when available.

Stage 8 also validates StateGraph path reachability and production invocation, cold/hot cache performance, cancellation and timeout behaviour, RBAC and adversarial inputs, deterministic browser E2E plus a limited real-LLM smoke test, and an empty-volume Docker cold start with recovery. The product currently contains ten current laws plus one historical index; deployment validates the complete released catalogue, while the main retrieval scorecard retains its documented eight-law scope.

## Release criteria

The final report cites only the frozen candidate's outputs. Dataset-review completeness, release quality gates, required E2E and Docker recovery checks must pass; P0 security/deployment issues and high-risk severe answer errors must be zero. Other metrics use thresholds declared after a development-set pilot and before frozen-test execution. Failures remain visible as limitations rather than being removed or relabelled.

