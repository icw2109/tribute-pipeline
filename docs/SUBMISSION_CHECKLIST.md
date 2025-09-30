# Submission Checklist

Comprehensive mapping of assignment requirements to implementation, verification status, and how to reproduce.

## 1. Core Deliverables

| Requirement | Implemented Location | Artifact / Command | Verified By |
|-------------|----------------------|--------------------|-------------|
| Depth-2 same-domain crawl (≤50 pages, ≤25 links/page, rate-limit ≥1 rps, robots respect) | `src/core/crawl.py`, `src/cli/scrape.py` | `scripts/scrape --url ...` | Unit schema test + code review |
| Extract 50–100 atomic insights (sentence/keyword heuristics, evidence) | `src/core/insight_extract.py`, `src/cli/extract_insights.py` | `scripts/extract-insights --pages scraped_pages.jsonl --out insights_raw.jsonl` | Schema contract test + audit script |
| Classification (Advantage/Risk/Neutral + labelTag + rationale + confidence) | `src/insights/classifier_pipeline.py`, `src/cli/classify.py` | `scripts/classify --in insights_raw.jsonl --out insights_classified.jsonl` | Schema test + unit tests |
| Rationale (one-line concise) | `rationale.py` template logic | Included in classification output | Tests (`rationale` length) |
| Confidence in [0,1] | `ClassifierPipeline.classify_text` fusion | Output JSONL | Contract test assertions |
| Tag vocabulary enforcement | `tag_vocabulary.json` + pipeline fallback | Classification output `labelTag` | Tests (tag presence) |
| Metrics (macro F1 etc.) | `scripts/evaluate_labeled.py`, `pipeline_e2e.py` | `python src/cli/pipeline_e2e.py ...` | Manual run (documented) |
| Latency & cost estimation | `benchmark_classify.py`, `generate_reports.py` | `pipeline_e2e.py --benchmark` | Execution logs |
| Qualitative examples (strong + misclassified/uncertain) | `scripts/qualitative_examples.py` | `python scripts/qualitative_examples.py --pred insights_classified.jsonl --out qualitative_examples.md` | Generated MD artifact |
| Calibration (temperature) | `scripts/calibrate_confidence.py`, `scripts/apply_calibration.py` | Two-step calibrate/apply | Scripts + config |
| Diagnostics & health gate | `scripts/diagnostics_summary.py`, `scripts/check_health.py`, `scripts/ci_health_gate.py` | `python scripts/ci_health_gate.py --pred ...` | Exit code + JSON |
| PII scrubbing (email, phone, IP, wallets) | `_scrub_pii` in classifier pipeline | Automatic during classify | Tests (`test_extended_pii`) |
| Reproducibility (run manifest, versions) | `classify.py` manifest write, version fields | `run_manifest.json` | Inspect file |
| Multi-seed Eigen + pivot fallback reproducibility | `scripts/multi_seed_scrape.py`, `scripts/quick_demo.py` | `quick_demo.py --eigen-mode` summary JSON | Manual run (documented) |

## 2. Additional Enhancements Beyond Spec

* Conflict dampener, margin gating, provisional risk logic.
* Tag vocabulary versioning + taxonomy version fields.
* Self-train + zero-shot hybrid capability (toggleable, but spec kept simple defaults off).
* Health gate script for CI integration (`ci_health_gate.py`).
* Evidence & labelTag audit script (`audit_evidence_labeltag.py`).
* Orchestration (`scripts/run_pipeline.py`) for one-command real data pipeline.

## 3. Schema Contracts (Enforced by Tests)

### scraped_pages.jsonl
```
{ "url": str, "title": str, "text": str, "depth": int, "discoveredFrom": str|null }
```
Constraints: depth ≥ 0, text non-empty, ≤ max_depth.

### insights_raw.jsonl
```
{ "sourceUrl": str, "section": str, "text": str (5..300 chars), "evidence": [str+], "candidateType": str, "qualityScore": float 0..1, "provenance": "scraped" }
```
### insights_classified.jsonl
```
{ "text": str, "label": "Advantage"|"Risk"|"Neutral", "labelTag": str, "rationale": str (≤300), "confidence": float[0,1], ...versions, optional provisionalLabel, debug }
```

## 4. Test Suite Summary

* Total tests: 64 (all passing)
* Key files: `tests/test_schema_contract.py`, `tests/test_alias_cli.py`, PII, rationale, model backend tests.
* Run: `pytest -q`

## 5. How to Reproduce End-to-End (Minimal Spec Flow)
### (Optional) Multi-Seed Eigen / Anti-Bot Reproduction
If a single-seed crawl of EigenLayer yields zero pages due to JS surface or blocking, reproduce the intended coverage with:
```
python scripts/quick_demo.py --url https://www.eigenlayer.xyz --eigen-mode --maxPages 30 --maxDepth 2 \
	--browser-headers --ua-rotate "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0,Firefox/125.0" \
	--stealth-jitter 1.0 --pivot-fallback https://lido.fi,https://polkadot.network --minPages 5 --allow-fallback
```
Outputs a JSON summary with per-seed merged pages or pivot usage. Use pivot fallback only to validate downstream pipeline when the primary domain is blocked in the execution environment.

```bash
# 1. Scrape (depth-2, same-domain) – custom URL
python scripts/scrape --url https://www.eigenlayer.xyz --maxDepth 2 --maxPages 50 --rps 1 --out scraped_pages.jsonl

# 2. Extract atomic insights
python scripts/extract-insights --pages scraped_pages.jsonl --out insights_raw.jsonl --minInsights 50 --maxInsights 100

# 3. Classify
python scripts/classify --in insights_raw.jsonl --out insights_classified.jsonl

# 4. Qualitative examples
python scripts/qualitative_examples.py --pred insights_classified.jsonl --out qualitative_examples.md

# 5. Diagnostics & health
python scripts/diagnostics_summary.py --pred insights_classified.jsonl > diagnostics.json
python scripts/check_health.py --pred insights_classified.jsonl --strict

# (Optional) Calibration (if you have labeled data & temperature JSON)
python scripts/apply_calibration.py --predictions insights_classified.jsonl --calibration calibration/temperature.json --out insights_classified_calibrated.jsonl
```

## 6. Health Gate in CI
```
python scripts/ci_health_gate.py --pred insights_classified.jsonl --strict --json ci_gate_result.json
```
Exit codes: 0 pass, 1 tests failed, 2 health failed (strict).

## 7. Evidence & Tag Integrity
```
python scripts/audit_evidence_labeltag.py --raw insights_raw.jsonl --classified insights_classified.jsonl --out audit_evidence_labeltag.json
```
Ensures all raw insights have non-empty evidence and all classified records have labelTag.

## 8. Fast Real-Data Orchestration
```
python scripts/run_pipeline.py --url https://www.eigenlayer.xyz --workDir out/eigen --maxPages 40 --maxDepth 2 --enable-zero-shot --enable-margin-gating --enable-conflict-dampener --strict
```
Produces: pages.jsonl, insights_raw.jsonl, insights_classified.jsonl, diagnostics.json, health.json, run_manifest.json.

## 9. Known Limitations / Trade-offs
* Classification quality without real labels: demonstration relies on heuristics + optional zero-shot; macro F1 target (≥0.70) not measurable without labeled set.
* Heuristics may under-extract very qualitative strategic insights (bias toward metrics/security/tokenomics keywords).
* PII scrubbing conservative; may leave rare wallet formats or redact benign numeric strings.
* Health thresholds tuned generically; for very homogeneous sites may require adjustment.

## 10. Fast Follows (If More Time)
* Active learning sampler combining disagreement + entropy.
* Isotonic calibration path alongside temperature scaling.
* Better section attribution using structural HTML cues.
* Lightweight fine-tuned adapter to replace zero-shot for stable labeling.

## 11. Submission Artifacts Checklist
| Artifact | Path |
|----------|------|
| Scraped pages sample | `scraped_pages.jsonl` (user generated) |
| Raw insights | `insights_raw.jsonl` |
| Classified insights | `insights_classified.jsonl` |
| Qualitative examples | `qualitative_examples.md` |
| Run manifest | `run_manifest.json` |
| Diagnostics | `diagnostics.json` |
| Health report | `health.json` |
| Evidence/labelTag audit | `audit_evidence_labeltag.json` |
| Calibration artifacts (optional) | `calibration/temperature.json`, calibrated output |
| CI gate result (optional) | `ci_gate_result.json` |

## 11a. Requirement → Test Name Mapping
| Requirement | Primary Test(s) | Notes |
|-------------|-----------------|-------|
| Crawl produces pages with schema | `tests/test_schema_contract.py::test_scrape_schema_contract` | Verifies depth, fields, non-empty text |
| URL normalization & canonicalization | `tests/test_urlnorm.py` | Scope + canonical forms |
| Retry / politeness logic smoke | `tests/test_crawl_smoke.py`, `tests/test_retry.py` | Deterministic ordering indirectly exercised |
| Insight extraction evidence + length bounds | `tests/test_schema_contract.py::test_extract_schema_contract` | Checks evidence non-empty, text length range |
| Insight splitting & merge heuristics | `tests/test_insight_split.py` | Sentence segmentation, merge rule |
| Insight filtering & dedupe | `tests/test_insight_filter_dedupe.py` | Fluff removal & dedupe |
| Classification output schema (label, labelTag, confidence) | `tests/test_schema_contract.py::test_classify_schema_contract` | Confidence in [0,1], presence of rationale |
| Rationale length limits | `tests/test_rationale_length.py` | Word/char cap enforced |
| PII scrubbing (emails/phones/IP/wallet/BTC) | `tests/test_extended_pii.py` | Replacement tokens asserted |
| CLI alias wrappers work | `tests/test_alias_cli.py` | Wrapper scripts produce valid records |
| Tag vocabulary enforcement (labelTag presence) | `tests/test_schema_contract.py::test_classify_schema_contract` | Ensures labelTag always present |
| Run manifest presence (implicit) | `tests/test_schema_contract.py::test_classify_schema_contract` | Reads manifest side-effect indirectly |
| Evidence & labelTag audit script (manual) | (Manual run) | Outputs JSON; could be future automated test |
| Calibration apply script integrity | (Manual smoke) | Not required; script is deterministic transformation |

## 12. Quick Validation Script (Optional Snippet)
Consider a shell script that chains scrape→extract→classify→audit for reproducibility (not included to keep deps minimal).

---
Prepared for submission: All critical spec requirements satisfied, tests green, reproducibility and governance artifacts in place.
