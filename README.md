# ResearchGraph AI

A foundation for scientific research gap discovery. Phase 2 adds OpenAlex paper search and selected-paper ingestion to the FastAPI service, migration-managed PostgreSQL/pgvector storage, and React dashboard. Embeddings, graph building, GNN training and hypotheses are not yet implemented.

## Requirements

Docker Compose, or Python 3.12, Node.js 22.12+ and PostgreSQL with the pgvector extension installed. No paid API is required.

## Start with Docker Compose

1. Copy `.env.example` to `.env`. Change the local database password if appropriate, and keep `POSTGRES_PASSWORD` and the password in `DATABASE_URL` consistent.
2. Run `docker compose up --build` from the project root. The backend runs migrations before starting.
3. Open http://localhost:5173. API documentation is at http://localhost:8000/docs.

If ports 5432 or 8000 are occupied, set `POSTGRES_PORT` and `BACKEND_PORT` in `.env` to free host ports and update `VITE_API_BASE_URL` to match the backend port. The services still use ports 5432 and 8000 internally. The database persists in a Docker volume. `/health` checks API process liveness only; it does not establish database readiness. The dashboard reports this endpoint's status, not the state of the research pipeline.

## Local development

Create a PostgreSQL database with pgvector available, then set `DATABASE_URL` to its connection string. From `backend`:

```sh
python -m venv .venv
# Activate the virtual environment for your shell
pip install -r requirements-dev.txt
alembic upgrade head
uvicorn app.main:app --reload
pytest
```

For PowerShell activate with `.venv\Scripts\Activate.ps1`. Settings are read from environment variables or a `.env` in the backend working directory. The migration enables `vector`; the database user needs permission to create that extension. Never use `create_all` as a production migration substitute.

From `frontend`:

```sh
npm install
npm run dev
npm test
npm run build
```

Set `VITE_API_BASE_URL` when the API is not on `http://localhost:8000`. Set `CORS_ORIGINS` to a JSON array of allowed browser origins. The root `.env` is used by Compose; for direct local runs export variables or create a backend `.env`.

## Structure

- `backend/app/api/v1`: versioned API routes; `/health` is unversioned liveness.
- `backend/app/core`, `db`, `models`, `services`: configuration/logging, database setup, persisted entities, and service boundary.
- `backend/app/research/interfaces.py`: contracts for ingestion, embeddings, graph building, link prediction and evidence-based generation. These are interfaces, not working research algorithms.
- `backend/migrations`: Alembic schema history, including pgvector enablement and paper metadata.
- `frontend/src`: responsive dashboard and real API health integration.

Future implementations should preserve source identifiers and citations, evaluate graph rankings against baselines, and use open models where practical. No GNN is trained in this phase.



## OpenAlex ingestion

Create and activate a free OpenAlex API key using [OpenAlex authentication](https://help.openalex.org/api/authentication/) and set `OPENALEX_API_KEY` in the ignored root `.env`. Restart the backend with `docker compose up -d backend` after changing it. Search is limited to 25 results per page and 50 pages; ingestion accepts at most 10 selected IDs per request. The backend fetches authoritative metadata itself. `GET /api/v1/openalex/search`, `POST /api/v1/papers/ingest`, `GET /api/v1/papers`, `GET /api/v1/papers/{id}`, and `GET /api/v1/ingestions` expose the workflow. A free key has a limited daily budget; respect OpenAlex usage terms and limits.

The paper's topic records its most recent ingestion query, rather than a complete topic taxonomy. Authors are stored as source metadata in a JSON array. DOI collisions with existing data cause migration or ingestion to fail rather than silently delete records. The ingestion request runs synchronously; runs and errors remain available through the API.

## Phase 3: corpus, embeddings and graph

The Papers page can start an explicitly requested background collection (maximum 1,000 results). Each page is committed with a checkpoint. Progress counts processed search results, including results that already existed; it is not a count of newly inserted papers. Failed or expired jobs can be resumed from the last checkpoint. Jobs running without a checkpoint for 10 minutes are marked interrupted when progress is next requested. The current worker lock is process-local: use a single backend worker and do not run multiple replicas. Search results can change between page requests, so page-based resumption is not a snapshot and may miss records.

Embeddings use `sentence-transformers/all-MiniLM-L6-v2` at revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, producing 384-dimensional normalized vectors on CPU. The first generation downloads model weights; Docker preserves them in `model_cache`. Use Generate embeddings on the Papers page, then Check embedding status. Generation is incremental and limited per request. Generation status is process-local and resets on restart; vectors persist in PostgreSQL.

The graph page explores a bounded neighborhood of saved papers. Its edges represent OpenAlex author and citation metadata or ingestion-query topic associations; absence of an edge is not evidence of a research gap. Citation references to papers outside the local library are stored but only relationships between saved papers appear in the graph. Authors lacking a stable OpenAlex ID remain in paper metadata and are not merged by name. Topic labels are user search queries, not OpenAlex taxonomy IDs.

Endpoints: `POST /api/v1/collections`, `GET /api/v1/collections`, `POST /api/v1/collections/{id}/resume`, `POST /api/v1/embeddings/generate`, `GET /api/v1/embeddings/status`, `GET /api/v1/semantic-search`, `GET /api/v1/graph/summary`, `GET /api/v1/graph/neighborhood`. Limits are enforced by the API.

Embedding generation scans papers in bounded pages and computes vectors in batches of at most 16. `EMBEDDING_CPU_THREADS` controls the CPU thread limit (default 2; accepted model setting is capped at 8). Completed vector batches remain persisted across interruptions; re-running generation reuses vectors whose source text and model revision are unchanged.

## Phase 4: exploratory GraphSAGE experiments

The Experiments page runs a bounded single-process CPU experiment; model artifacts are saved under the ignored `backend/artifacts` directory. An experiment snapshots the current local OpenAlex citation graph and pinned 384-dimensional embeddings. Its SHA-256 dataset identifier covers sorted IDs, years, all local directed citation edges and feature bytes; checkpoint contains the split and model parameters. Input data are not snapshotted separately, so retain the original dataset to reproduce the hash.

This is an **exploratory random-edge split**, not a temporal or prospective benchmark. Only source→target edges where target publication year is strictly earlier are eligible as positives; same-year and later-year references are preserved but excluded. The 70/15/15 seeded split applies to eligible edges. Training-only directed edges and their reverses form the message-passing graph; validation and test edges are absent in both directions. A directional source/target projection decoder scores candidate citations. The ingestion-query topic and author nodes are excluded. Current text embeddings may contain later changes and are not historical snapshots.

Training, validation and test unlabeled pairs are reproducibly sampled without replacement, one per positive, with the source newer than the target; all observed citations across the snapshot are excluded from those samples, which uses the full observed-positive set for filtering. This is not ground-truth negative labeling. Sampled ROC-AUC and average precision use a balanced set and should not be read as corpus-prevalence results. Ranking metrics average per test source over all older local targets, excluding other observed citations but retaining all test positives for that source; ties follow stable paper-ID ordering. Cold-start means a test source has zero degree in the training citation graph. Best validation loss selects the checkpoint.

GraphSAGE uses two mean-aggregation SAGE layers, ReLU and dropout, with separate linear source and target projections. Baselines use the same test positives, unlabeled samples and ranking pools: original embedding cosine similarity, target in-degree on training citations, and common neighbors / Adamic–Adar on the undirected training projection. No method uses citation counts as a feature. Candidate scores are uncalibrated and denote hypotheses only; current observed citations are filtered at serving time. The service currently assumes one backend worker and progress may be marked running after interruption.

API: `GET /api/v1/experiments/configuration`, `POST /api/v1/experiments`, `GET /api/v1/experiments`, `GET /api/v1/experiments/{id}`, and `GET /api/v1/experiments/{id}/candidates`. See `backend/reports` for the temporal anomaly list and the heuristic domain screen; no paper or source edge was removed.

## Phase 4.5: reliability and repeated evaluation

Experiments use validation-loss early stopping (default patience 6, minimum improvement 0.0001), restore the best weights, and clip gradient norm to 1. CPU PyTorch threads are capped at two. PostgreSQL advisory ownership and a local lock prevent simultaneous experiment workers from sharing a run; a running record with no owner is marked interrupted on the next experiment listing or start. Checkpoints use experiment-specific paths and atomic replacement. Interrupted runs are not automatically resumed.

The five-seed validation-only search and exploratory evaluations are recorded in `backend/reports/phase45_validation_search.json`, `phase45_repeated_results.json`, and `phase45_evaluation.md`. Each split selected among three small configurations using only its validation loss. Filtered comparisons reuse that seed's full-corpus selected configuration; excluding papers changes the edge split and candidate pool, so differences cannot be attributed solely to relevance. The five random splits overlap substantially; their t-based intervals are descriptive variability summaries, not independent or prospective confidence intervals.

`domain_review_phase45.csv` reviews the 64 titles flagged by the original screen: four clearly non-domain titles are excluded by a narrow title rule, three titles are relevant to chemical or molecular work, and 57 are uncertain. These are transparent title rules, not expert judgments. The optional `domain_filter` excludes only paper IDs 301, 396, 445 and 504 from an experiment without changing the original database.

Candidate evidence records current-text cosine, training-graph shared-neighbor count, target training in-degree and years; these are indicators, not verified missing citations. Popularity sorting reorders the stored model-selected candidate set and does not constitute an independent global popularity top-100. The saved candidate ranks use deterministic paper-ID tie breaks. Historical evaluation remains unsupported: current abstracts and embeddings, metadata updates, graph relationships, and the all-observed-positive filter are not reconstructed as of a historical cutoff.

## Phase 5: evidence-grounded candidate review

The Research Gaps page inspects a saved experiment candidate, retrieves a bounded evidence snapshot, and can save a deterministic review. Retrieval combines the pinned pgvector model, title-keyword ranking and OpenAlex citation references via reciprocal-rank fusion. The first two records are the selected candidate papers. An optional external OpenAlex query performs one search with at most three HTTP attempts and returns at most five results; it never inserts those results into the corpus. The total evidence limit is 2–15 records. External search is skipped when the limit leaves no room beyond the candidate pair.

The provider interface is configurable through `ANALYSIS_PROVIDER`; only `deterministic` is currently implemented. There is no configured generative model or paid provider. Unknown provider names return an error. The deterministic provider lists citation-linked source metadata and poses a generic tentative question; it does not establish scientific support, contradiction, novelty, or an actual gap. Its statuses are `unable to assess` or `insufficient evidence` because no scientific synthesis has been adjudicated. Title-term overlap is only a retrieval cue.

Each saved evidence record includes its OpenAlex ID, DOI when available, authors, year, abstract state, local/external origin and retrieval methods. Evidence references such as E1 are checked against the saved snapshot; OpenAlex IDs and DOIs are syntax-checked. An optional citation check contacts only the DOI resolver without following redirects; this does not verify the publisher page or full-text access. No full texts are inspected. Identifier matching is not evidence that a source supports a claim. All scientific overlap, contradictions and hypotheses require human full-text review.

Endpoints: `GET /api/v1/analysis/providers`, `GET /api/v1/analysis/evidence`, `POST /api/v1/analyses`, `GET /api/v1/analyses`, and `GET /api/v1/analyses/{id}`, and `GET /api/v1/analyses/{id}/citations/{citation_id}/verify`. Analysis jobs use a database advisory lock, with interrupted jobs marked when history is next requested or a new run is started. Evidence retrieval is limited to one concurrent request per backend process. For the small real-data evaluation and its limitations, see `backend/reports/phase5_evaluation.md`.

## Phase 5.5: optional Gemini structured generation

The default remains the local deterministic summary. To opt in, create a Gemini API key in [Google AI Studio](https://aistudio.google.com/apikey) for a project that has **no billing account linked** and is eligible for Gemini's free tier. Add `GEMINI_API_KEY` and `GEMINI_FREE_TIER_CONFIRMED=true` to the ignored root `.env`, then run `docker compose up -d backend`. The confirmation is a user assertion: this application cannot independently verify Google project billing status, so do not enable it for a billed project without approval. Never paste keys into chat or commit `.env`. Google says free-tier content may be used to improve its products; selecting Gemini sends bounded paper titles and abstracts to Google.

The provider is `gemini-3.5-flash-lite`; only this allowlisted model is supported. It sends at most eight records and 12,000 UTF-8 bytes of evidence, truncates each abstract to 1,500 characters, requests at most 2,048 output tokens, uses a 35-second request timeout and makes no retries. The application persists a ledger of all attempts and caps them at five per UTC day by default (including failed and interrupted attempts); Google may enforce lower quotas. This local cap does not verify billing or guarantee provider pricing. There is no web-search grounding or paid tool use.

Structured outputs are schema-validated and checked against the IDs actually sent to the model. Unknown evidence IDs, uncited structured statements, bibliographic URLs or DOI strings in generated text, malformed output, and failure to abstain on an insufficient evidence set are rejected. Failures produce the existing deterministic fallback with a reason; no failed model output is published. Evidence IDs matching the supplied records do not prove the evidence supports the text. Full-text review and independent scientific assessment remain necessary.
