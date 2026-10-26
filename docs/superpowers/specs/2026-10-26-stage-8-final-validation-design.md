# LexRAG Stage 8 final validation design

## Purpose

Stage 8 converts the engineering-closed v3.0 codebase into one auditable release candidate. It does not add product features, agents, model providers, or microservices. The release conclusion must be reproducible from a single commit, data snapshot, runtime configuration, and report set.

## Scope and sequencing

The implementation is organised as a release train: first close the explicit Stage 6 carry-overs, then establish governed evaluation data and a shared run manifest, then execute retrieval, workflow, human-review, performance, security, browser, Docker, and release gates on the frozen candidate. A defect creates a new candidate and invalidates the affected downstream evidence; reports from different candidates are never combined.

## Data and evaluation contract

The existing 100-row eight-law file is provisional because 85 rows claim `approved` status while their source records still say pending review. Stage 8 will preserve the historical files, restore those rows to an auditable review workflow, and publish a new frozen 300-row statute retrieval dataset. Each row records question, type, difficulty, expected knowledge bases, relevant articles, abstention expectation, source URL/version/location, reviewer, date, and review note. Development samples may inform fixes; frozen test labels cannot be altered to fit system output.

Every evaluator emits the same per-item schema with retrieval contexts, response, citations, workflow trace, token usage, latency, run identity, and explicit execution errors. A run manifest binds those results to Git SHA, legal-source hashes, embedding and chunking versions, collection identifiers, model configuration, and dependency versions.

## Verification design

Retrieval comparisons run paired configurations on the frozen dataset: BM25, vector, RRF, rewrite, graph expansion, optional reranker, and the complete workflow. Reporting includes ranking, routing, abstention, contamination, latency, and paired uncertainty/statistical tests. Reranking remains disabled unless the frozen evaluation shows a reproducible quality benefit that justifies its resource cost.

One hundred stratified full-workflow answers receive evidence-located human review for legal correctness, support, citation fidelity, completeness, abstention, and severe error. Ragas and a fixed Judge configuration are diagnostic only and are calibrated against that human subset; neither replaces legal review. A solo-review fallback is interval re-review with explicitly limited claims; two blinded reviewers are used only when available.

Stage 8 also validates StateGraph path reachability and production invocation, cold/hot cache performance, cancellation and timeout behaviour, RBAC and adversarial inputs, deterministic browser E2E plus a limited real-LLM smoke test, and an empty-volume Docker cold start with recovery. The product currently contains ten current laws plus one historical index; deployment validates the complete released catalogue, while the main retrieval scorecard retains its documented eight-law scope.

## Release criteria

The final report cites only the frozen candidate's outputs. Dataset-review completeness, release quality gates, required E2E and Docker recovery checks must pass; P0 security/deployment issues and high-risk severe answer errors must be zero. Other metrics use thresholds declared after a development-set pilot and before frozen-test execution. Failures remain visible as limitations rather than being removed or relabelled.

