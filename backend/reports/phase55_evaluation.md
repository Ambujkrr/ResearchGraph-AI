# Phase 5.5 Gemini Structured Generation Evaluation

Evaluation of the bounded Google Gemini Flash-Lite (`gemini-3.5-flash-lite`) integration against real candidate pairs from GraphSAGE Experiment 9. All calls adhere to unbilled free-tier constraints, local rate limiting, citation grounding, schema validation, and deterministic fallback.

## Evaluated Cases

| Analysis | Case Description | Requested / Effective Provider | Status | Hypothesis / Design | Citation IDs Valid | Safeguards Triggered |
|---:|---|---|---|---|:---:|---|
| **8** | Related literature synthesis (source 240 → target 460, top_k=8) | `gemini` / `gemini-3.5-flash-lite` | existing related research found | Generated (E1, E2) | Yes | Bounded context (2,062 input tokens, 535 output tokens, 10.08s) |
| **9** | Candidate source missing abstract (source 94 → target 460, top_k=8) | `gemini` / `gemini-3.5-flash-lite` | insufficient evidence | Abstained (null / null) | Yes | Abstention safeguard: E1 metadata-only, no abstract |
| **10** | Restricted evidence budget (source 352 → target 460, top_k=2) | `gemini` / `gemini-3.5-flash-lite` | insufficient evidence | Abstained (null / null) | Yes | Abstention safeguard: top_k=2 (fewer than 3 records) |
| **7** | Deterministic fallback on provider error | `gemini` → `deterministic_metadata_summary` | unable to assess | Deterministic question | Yes | Fallback on HTTP error with preserved reason |

## Verification Details

### 1. Citation Grounding & Structured Synthesis (Analysis 8)
- **Candidate Pair**: MolGpKa (`W3181755904`) → Neural Message Passing for Quantum Chemistry (`W2606780347`).
- **Generated Hypothesis**: *"Integrating the graph-convolutional architecture used in MolGpKa with the generalized Message Passing Neural Network (MPNN) framework can improve the predictive accuracy of molecular pKa estimation across diverse chemical datasets compared to using standard fingerprint-based machine learning models alone."*
- **Citations**: Strictly grounded to `E1` and `E2`. Every claim in `claims`, `supporting_evidence`, `hypothesis`, and `uncertainties` maps exclusively to valid evidence identifiers.
- **Validation Experiment**: Feasible experimental design proposing a joint message-passing GNN evaluated on benchmark datasets (such as ChEMBL) reporting RMSE and MAE against baseline fingerprints.
- **DOI Verification**: Subsequent check on `E1` (`10.1021/acs.jcim.1c00075`) and `E2` returned HTTP 302 without following redirects.

### 2. Abstention on Missing Abstract (Analysis 9)
- **Candidate Pair**: MD-GNN (`W4375946946`) → Neural Message Passing for Quantum Chemistry (`W2606780347`).
- **Condition**: Source paper E1 had no abstract available in OpenAlex metadata.
- **Outcome**: The model correctly abstained, returning `review_status: "insufficient evidence"`. In compliance with schema rules, `hypothesis` and `validation_experiment` were set to `null`.
- **Uncertainty Grounding**: Grounded uncertainty note cited `E1` and `E2`, noting that E1 lacks abstract text and requires full-text review.

### 3. Abstention on Bounded Evidence Budget (Analysis 10)
- **Candidate Pair**: Decoupling Depth and Scope (`W3214086726`) → Neural Message Passing for Quantum Chemistry (`W2606780347`).
- **Condition**: Deliberately restricted `top_k=2`.
- **Outcome**: Correctly abstained with `review_status: "insufficient evidence"`, `hypothesis: null`, and `validation_experiment: null`.

### 4. Deterministic Fallback & Error Handling (Analysis 7)
- **Scenario**: Provider encountered an error during dispatch.
- **Outcome**: The analysis completed gracefully by invoking `DeterministicProvider()`. The fallback response clearly recorded `fallback_reason: "Gemini request failed with HTTP 404"` and `requested_provider: "gemini"`. No model hallucinations or unhandled exceptions occurred.

### 5. Daily Ledger & Free-Tier Guardrails
- **Ledger Persistence**: 4 generation attempts recorded in the `generation_attempts` table (`1 failed`, `3 completed`).
- **Quota Protection**: Daily cap enforced at `min(limit, 5)` requests per UTC day.
- **Context Boundaries**: Truncation to 8 records, 12,000 UTF-8 bytes max, 1,500 characters per abstract, 2,048 output tokens, and 35-second single-attempt timeout with zero retries.
