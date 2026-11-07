# Phase 5 evidence review evaluation

Three real stored candidate pairs; no expert relevance labels or full-text adjudication were fabricated. Analysis 6 deliberately used top_k=2, so it measures abstention under a restricted evidence budget rather than a naturally empty search.

| Case | Analysis | Evidence | Related | Abstracts | External | OpenAlex ID syntax valid | Metadata claims matching cited title | Review status |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| related literature via an observed OpenAlex citation | 4 | 8 | 6 | 7 | 0 | 8 | 8/8 | unable to assess |
| ambiguous relationship with external metadata | 5 | 8 | 6 | 6 | 3 | 8 | 8/8 | unable to assess |
| limited-evidence / abstention (top_k=2) | 6 | 2 | 0 | 2 | 0 | 2 | 2/2 | insufficient evidence |

Analysis 4 contains a record retrieved via an observed OpenAlex citation. Its related-title term overlap is a retrieval cue only. Analysis 5 includes three external metadata records; their scientific relevance and any overlap remain unadjudicated. Analysis 6 has no additional retrieved papers because its limit was two.

All internal citation IDs matched included evidence and OpenAlex identifiers passed syntax checks; source links were not checked as part of these snapshots, and no full texts were verified. A separate later DOI resolver check for Analysis 4 E1 returned HTTP 302 without following the redirect. Exact title matching assessed deterministic metadata claims only, not scientific support. Relevance precision and a scientific unsupported-claim rate cannot be estimated without independently judged examples.
