# Tribute Takehome

> Quick Start (Single Command)
>
> 1. Create & activate a virtual environment (PowerShell on Windows):
>    ```powershell
>    python -m venv .venv
>    .\.venv\Scripts\Activate
>    pip install -r requirements.txt
>    ```
> 2. Run the entire crawl → extract → classify → diagnostics → health → validation pipeline with one command:
>    ```powershell
>    python scripts/run_pipeline.py --url https://example.com --all
>    ```
>    This automatically: creates a timestamped work directory, enables zero‑shot + self‑train + gating features, runs diagnostics, health gate, strict validation, and prints a human summary plus machine JSON.
> 3. Inspect the generated folder under `out/` (e.g. `out/run_20250101_120301/`). Key artifacts:
>    - `pages.jsonl` (raw crawl)
>    - `insights_raw.jsonl` (extracted insight candidates)
>    - `insights_classified.jsonl` (final labeled insights w/ rationale & confidence)
>    - `diagnostics.json` (label distribution, neutrality ratio, confidence bins)
>    - `health.json` (health gate status: 0=pass, 1=soft warning, 2=fail)
>    - `summary` (printed to console + JSON at end of run)
>    - `run_manifest.json` (reproducibility metadata written by classify)
>
> Sample final JSON (abridged):
> ```jsonc
> {
>   "url": "https://example.com",
>   "records": 87,
>   "label_dist": {"Advantage": 41, "Risk": 29, "Neutral": 17},
>   "neutral_ratio": 0.195,
>   "health_status": 1,
>   "validation_status": "pass",
>   "samples": [
>     {"label": "Risk", "confidence": 0.91, "text": "Operators may be slashed if..."},
>     {"label": "Advantage", "confidence": 0.88, "text": "Protocol offers restaking incentives..."}
>   ]
> }
> ```
> Interpretation: `health_status` 1 = soft distribution warning (run succeeds unless `--strict`); `validation_status` pass means schema & consistency checks succeeded.
>
> Legacy: `run_all.py` remains for backward compatibility but is superseded by `scripts/run_pipeline.py --all`.
>
> For multi-seed Eigen demo or granular flags, read on.

Two clearly separated phases:

**Part 1 – Crawler**: Deterministic, polite BFS site collector producing `scraped_pages.jsonl`.

**Part 2 – Insight Extraction**: Heuristic pipeline converting scraped raw text into atomic investor-relevant insights (`insights_raw.jsonl`).

---
## Requirements → Implementation Mapping (Spec Coverage)

| Requirement | Implementation (Key Files) | Verification (Tests / Scripts) | CLI / Script Usage |
|-------------|----------------------------|--------------------------------|--------------------|
| Polite depth-limited same-domain crawl (≤ depth 2, page cap, RPS, robots) | `src/core/crawl.py`, `src/cli/scrape.py`, `src/core/robots.py`, `src/core/urlnorm.py` | `tests/test_crawl_smoke.py`, `tests/test_urlnorm.py`, stats output | `python src/cli/scrape.py ...` / `scripts/scrape` |
| Deterministic BFS ordering & duplicate suppression | `crawl.py` (sorted frontier, canonical URL set) | `test_crawl_smoke.py` (stable count), normalization tests | Same as above |
| Clean text extraction & boilerplate removal | `src/core/boilerplate.py` | Indirect via insight extraction tests | Crawl stage |
| Atomic insight extraction (50–100) w/ evidence + quality heuristics | `src/core/insight_extract.py` | `tests/test_insight_split.py`, `tests/test_insight_filter_dedupe.py`, schema contract tests | `src/cli/extract_insights.py` / `scripts/extract-insights` |
| Insight schema (sourceUrl, section, text len bounds, evidence[]) | `insight_extract.py` | `tests/test_schema_contract.py::test_extract_schema_contract` | Extraction step |
| Classification (Advantage/Risk/Neutral) | `src/insights/classifier_pipeline.py` | `tests/test_schema_contract.py::test_classify_schema_contract` | `src/cli/classify.py` / `scripts/classify` |
| Sub-tag / labelTag vocabulary enforcement | `tag_vocabulary.json`, classifier fallback | Tag presence tests & schema tests | Classification step |
| Deterministic concise rationale (word/char cap) | `src/insights/rationale.py` | `tests/test_rationale_length.py` | Classification step |
| Confidence score [0,1] + fusion logic | `classifier_pipeline.py` | Schema contract confidence assertions | Classification step |
| PII scrubbing (email, phone, IPv4, wallet, BTC) | `_scrub_pii` in `classifier_pipeline.py` | `tests/test_extended_pii.py` | Automatic during classify |
| Versioning (schemaVersion, taxonomyVersion, tag vocab version) | `classify.py` manifest writer | Manifest inspection + schema tests | Classification output |
| Run manifest reproducibility (hash, config, env) | `classify.py` (manifest write) | Manual inspection; stable key names | Produced with classify |
| Diagnostics (distribution, confidence bins, provenance) | `scripts/diagnostics_summary.py` | Invoked in pipeline / manual | `python scripts/diagnostics_summary.py --pred ...` |
| Health gate (neutral bounds, min support) | `scripts/check_health.py`, `scripts/ci_health_gate.py` | Health JSON status & exit codes | `python scripts/check_health.py --pred ...` |
| Calibration (temperature apply) | `scripts/apply_calibration.py` | Unit usage + manual test (if calibration JSON) | `python scripts/apply_calibration.py ...` |
| Qualitative examples (strong, uncertain, misclassified) | `scripts/qualitative_examples.py` | Manual review of `qualitative_examples.md` | `python scripts/qualitative_examples.py --pred ...` |
| Evidence & labelTag completeness audit | `scripts/audit_evidence_labeltag.py` | Audit JSON output (all pass) | `python scripts/audit_evidence_labeltag.py ...` |
| CI gate (tests + health) | `scripts/ci_health_gate.py` | Exit codes (0 pass) | `python scripts/ci_health_gate.py --pred ...` |
| End-to-end orchestration | `scripts/run_pipeline.py` | Integration smoke run | `python scripts/run_pipeline.py ...` |
| Artifact regeneration (one-command refresh) | `scripts/regenerate_artifacts.py` (added) | Generates summary JSON & artifacts | `python scripts/regenerate_artifacts.py ...` |
| Multi-seed crawl + pivot fallback (Eigen) | `scripts/multi_seed_scrape.py`, `scripts/quick_demo.py` | Manual run summary JSON (counts) | `python scripts/quick_demo.py --eigen-mode ...` |

For a narrative checklist see `docs/SUBMISSION_CHECKLIST.md`.

### Synthetic Health Gate Demo
### Multi-Seed Eigen Mode & Anti-Bot Workarounds

Some production sites (e.g., EigenLayer) surface substantive documentation under alternate subdomains (including `eigencloud.xyz`) and may apply lightweight anti-bot filtering causing zero-page captures for a naïve single-seed crawl. To mitigate:

1. Multi-Seed Enumeration: Crawl main + docs + blog across both `eigenlayer.xyz` and `eigencloud.xyz` domains and merge.
2. User-Agent Rotation: Supply a small pool of common browser UA strings to avoid being bucketed by a single bot UA.
3. Browser Headers: Enable `--browserHeaders` for realistic Accept / Language negotiation.
4. Stealth Jitter: Randomize short sleeps between seed scrapes (`--stealthJitter`) so timing patterns are less uniform.
5. Pivot Fallback: If all primary seeds yield 0 pages (possible hard block), optionally pivot to alternate staking ecosystems (e.g., `https://lido.fi`, `https://polkadot.network`) simply to exercise end-to-end pipeline behavior.

Example (Eigen multi-seed):
```bash
python scripts/quick_demo.py \
  --url https://www.eigenlayer.xyz \
  --eigen-mode \
  --maxPages 30 --maxDepth 2 \
  --browser-headers \
  --ua-rotate "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125 Safari/537.36,Firefox/125.0" \
  --stealth-jitter 1.5 \
  --pivot-fallback https://lido.fi,https://polkadot.network \
  --minPages 5 --allow-fallback
```

Direct multi-seed script usage (fine-grained control):
```bash
python scripts/multi_seed_scrape.py \
  --seeds https://www.eigenlayer.xyz,https://docs.eigenlayer.xyz,https://blog.eigenlayer.xyz,https://docs.eigencloud.xyz,https://blog.eigencloud.xyz \
  --out data/eigen_all.jsonl --maxPagesPerSeed 12 --maxDepth 2 --rps 1 \
  --uaRotate "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_4) AppleWebKit/605.1.15 Safari/605.1.15,Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/125.0.0.0" \
  --stealthJitter 1.0 --robotsFallbackAllow --browserHeaders \
  --pivotFallback https://lido.fi,https://polkadot.network
```

The script prints a JSON summary including per-seed counts, whether a pivot fallback was used, UA rotation flag, and final unique page total.

If you repeatedly see `unique_pages: 0`, the environment may be blocked; in that case rely on the pivot fallback to validate downstream extraction/classification while documenting the block.

Demonstrate CI health gate behavior on a balanced synthetic set without running the full pipeline:

```bash
python scripts/generate_synthetic_predictions.py --out synthetic_balanced.jsonl --per-class 40
python scripts/ci_health_gate.py --pred synthetic_balanced.jsonl --strict
```

Expected: exit code 0 (healthy distribution, tests pass). Skew counts manually (e.g., delete most Risk lines) to observe a non‑zero health status.

---
## Part 1: Crawler

### Features
- Deterministic BFS (sorted unique outbound links) up to depth 2 (configurable)
- Domain + subdomain scoping (in-scope: host endswith seed registrable domain)
- URL normalization & canonicalization (lowercase scheme/host, strip fragments & tracking params, trim trailing slash on non-root paths)
- Robots.txt respect + global RPS rate limiting
- Per-page outbound link cap
- Structured stats & JSON event logging (`--stats`, `--verbose`, `--logEvents`)
- Retry with exponential backoff on transient HTTP errors (429, 5xx)
- Clean text extraction with boilerplate removal (nav, footer, cookie banners)
- JSONL streaming output (stable schema)
- Test suite with smoke, normalization, canonicalization, and retry behavior
- Optional content hash dedupe (`enable_content_dedupe`)
- HTML size guard (`max_html_bytes`) to skip very large pages

### Project Structure (Crawler + Insights)
```
src/
  core/
    crawl.py        # Crawl engine (BFS, retries, stats, events)
    urlnorm.py      # URL normalization + scope + canonicalization
    boilerplate.py  # HTML → (title, text) extraction
    robots.py       # robots.txt caching + can_fetch
    iojsonl.py      # JSONL read/write helpers
    config.py       # CrawlConfig dataclass
  cli/
    scrape.py       # Command-line entrypoint for crawling
    summary.py      # Summarize a JSONL file (counts, domains, depths)
    truncate.py     # Truncate JSONL to first N rows with optional text shortening
```

### Installation
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .\.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
```

### Crawl CLI Usage
#### Basic Crawl
```bash
python src/cli/scrape.py \
  --url https://www.eigenlayer.xyz \
  --maxDepth 2 \
  --maxPages 50 \
  --rps 1 \
  --perPageCap 25 \
  --out data/eigenlayer.jsonl \
  --stats
```

#### Stream Records While Writing
```bash
python src/cli/scrape.py --url https://example.com --maxDepth 0 --maxPages 1 --out data/example.jsonl --echo --stats
```

#### Verbose Event Log + File Logging
```bash
python src/cli/scrape.py --url https://example.com \
  --maxDepth 1 --maxPages 5 \
  --out data/example.jsonl \
  --verbose \
  --logEvents data/events.jsonl \
  --stats
```

#### Summarize Output
```bash
python src/cli/summary.py data/eigenlayer.jsonl --show 3
```

#### Truncate Output
```bash
python src/cli/truncate.py --in data/eigenlayer.jsonl --out data/eigenlayer.small.jsonl --limit 10 --maxTextChars 500 --pretty
```

### Crawler Output Schema
Each line in output JSONL:  
```json
{
  "url": "https://docs.eigenlayer.xyz/...",
  "title": "Operators | EigenLayer Docs",
  "text": "Visible cleaned text ...",
  "depth": 1,
  "discoveredFrom": "https://www.eigenlayer.xyz/"
}
```

### Stats (example)
Printed with `--stats` to stderr. Keys may appear as they become non-zero:
```json
{"fetched_ok":42,"skipped_robots":1,"skipped_off_scope":3,"skipped_non_html":2,"errors_fetch":0,"duplicates":17,"duplicates_content":4,"skipped_too_large":2,"enqueued":95}
```

Stats fields:
- `fetched_ok`: pages successfully fetched & yielded
- `skipped_robots`: blocked by robots.txt
- `skipped_off_scope`: redirected or discovered out of scope
- `skipped_non_html`: non-HTML content types
- `errors_fetch`: exhausted retries / network errors
- `duplicates`: URL-level duplicate enqueues avoided (already seen canonical URL)
- `duplicates_content`: pages whose (normalized) text content hash already seen (requires `enable_content_dedupe`)
- `skipped_too_large`: pages skipped because raw HTML bytes exceeded `max_html_bytes`
- `enqueued`: total pages enqueued (breadth-first frontier)

### Event Log (sample lines)
```json
{"type":"fetched","url":"https://example.com/","depth":0,"title_len":14,"text_len":512}
{"type":"enqueued","url":"https://example.com/page","parent":"https://example.com/","depth":1}
{"type":"retry","url":"https://example.com/api","status":503,"attempt":1,"backoff":0.75}
```

### Retry Logic
- Retries status codes: 429, 500, 502, 503, 504
- Attempts: `retry_attempts` (default 3)
- Backoff: `retry_backoff_base * 2^attempt` (default base 0.75s)

### Extending (Crawler)
| Area | How |
|------|-----|
| Add exclusion patterns | Filter in `_same_domain_links` or pre-enqueue |
| Add checksum/dup by content | Hash normalized text, skip repeats |
| Add dynamic page detection | Flag short text with presence of `__next` or large script ratio |
| Add insight extraction | Create `insights/` pipeline consuming JSONL lines |
| Add concurrency | Replace loop with async tasks + semaphore, maintain ordering if needed |

### Testing (Crawler + Shared)
Run all tests:
```bash
pytest -q
```
Key tests:  
- `test_urlnorm.py` – normalization, scope, canonical  
- `test_crawl_smoke.py` – end-to-end single page  
- `test_retry.py` – retry/backoff path  

### Design Choices (Crawler)
- Determinism: Sorting links ensures reproducible BFS ordering.
- Simplicity over early abstraction: single-threaded, minimal deps.
- Separation of concerns: extraction (boilerplate) isolated from navigation (crawl).
- Event callback lets you plug metrics/telemetry without changing core logic.

### Potential Future Improvements (Crawler)
1. Configurable HTML parser fallback (lxml → html5lib fallback)  
2. Structured logging via a proper logger adapter  
3. Pluggable link filters (e.g., MIME guess, extension blacklist)  
4. Adaptive politeness (slow down on consecutive 429s)  
5. Partial incremental re-crawl with ETag/Last-Modified  
6. Finer-grained MIME/content sniffing prior to fetch for bandwidth savings  

---
---
## Part 2: Insight Extraction

`scraped_pages.jsonl`  →  `insights_raw.jsonl`

Transforms raw page text into 50–100 concise, investor-useful, traceable insight records.

### Pipeline Stages
1. Load & Iterate: Stream each scraped record.
2. Cleaning: Remove boilerplate (cookies, newsletter, footers).
3. Sentence / Bullet Split: Split on `.?!` and bullet markers (• - –) while dropping ultra-short fragments.
4. Candidate Filtering: Keep sentences containing metrics (numbers, %), crypto / protocol keywords, or risk/security terms; drop fluff.
5. Adjacent Merge: Merge a qualifying short follower sentence if it shares a keyword.
6. Evidence Capture: Original sentence(s) stored for traceability.
7. Deduplication: Lowercased alphanumeric normalization; (future fuzzy dedupe).
8. Truncation: Cap to `--max` insights (default 100).

### Directory Structure (Insights)
```
src/insights/
  pipeline.py    # All extraction primitives + driver
  __init__.py    # Re-exports public API
src/cli/insights.py  # CLI entrypoint
```

### Insight CLI Usage
```bash
python src/cli/insights.py scraped_pages.jsonl insights_raw.jsonl --min 50 --max 100
```

### Insight Output Schema
```json
{
  "sourceUrl": "https://docs.eigenlayer.xyz/restaking/overview",
  "section": "restaking",
  "text": "EigenLayer allows ETH to be restaked, extending security to new protocols.",
  "evidence": [
    "EigenLayer allows ETH to be restaked.",
    "Extending security to new protocols."
  ]
}
```

`section` = first path segment or `root`.

### Current Insight Heuristics
| Aspect | Rule |
|--------|------|
| Noise removal | Regex lines (cookies, signup, newsletter, legal) dropped |
| Filtering | Must have number OR crypto keyword OR risk term |
| Fluff rejection | Regex of marketing adjectives |
| Merge rule | IF next sentence <80 chars AND shared keyword |
| Length guard | Discard >300 char merged strings |
| Dedupe | Exact normalized text (lowercase alphanumeric) |

### Tests (Insights)
| File | Purpose |
|------|---------|
| `test_insight_split.py` | Cleaning, splitting, merge heuristic sanity |
| `test_insight_filter_dedupe.py` | End-to-end extract + dedupe + fluff filter |

### Future Enhancements (Insights)
| Area | Next Step |
|------|-----------|
| Fuzzy dedupe | MinHash / Jaccard / cosine similarity |
| Category balancing | Thematic buckets & quota enforcement |
| NER / Proper nouns | spaCy or simple capitalized sequence heuristics |
| Metric structuring | Parse numbers/% into structured fields |
| Risk tagging | Lightweight classifier probability |
| Evidence spans | Char offsets into original text |
| Confidence scoring | Combine frequency + uniqueness + keyword weight |

---
## Combined Workflow
1. Crawl: produce `scraped_pages.jsonl`.
2. Extract: run insights CLI to produce `insights_raw.jsonl`.
3. (Future) Categorize / rank / synthesize summary deck.

---
## Quick Commands
```bash
# Crawl
python src/cli/scrape.py --url https://example.com --maxDepth 1 --maxPages 30 --out scraped_pages.jsonl --stats

# Extract insights
python src/cli/insights.py scraped_pages.jsonl insights_raw.jsonl --min 50 --max 100
```

---
All parts now separated: Part 1 (crawler) in `core/`, Part 2 (insights) in `insights/`.

## Insight Extraction (Phase 2)

The insight pipeline converts raw `scraped_pages.jsonl` into investor-relevant, atomic insights (`insights_raw.jsonl`).

### Pipeline Stages
1. Load & Iterate: Stream each scraped record (url, title, text, depth, discoveredFrom).
2. Cleaning: Remove boilerplate noise lines (cookie banners, newsletter prompts, generic footers).
3. Sentence/Bullet Split: Regex split on sentence terminators and bullet markers (`• - –`). Short fragments (<5 chars) dropped.
4. Candidate Filtering: Keep sentences containing either:
   - Numbers / metrics (percentages, years, amounts)  
   - Crypto / protocol keywords (restaking, validator, slashing, operator, emission, tokenomics, governance, incentive, risk, security, TVL)  
   - Risk/security terminology (risk, penalty, slashed, audit)
   Fluff ("world-class", "innovative") discarded.
5. Adjacent Merge: Merge a sentence with its immediately following short qualifier sentence when they share a domain keyword (heuristic ≤ 80 chars for the second sentence).
6. Evidence Capture: For each merged insight, store original sentence(s) as evidence list.
7. Deduplication: Normalize lowercase alphanumerics and collapse exact repeats. (Future: fuzzy similarity.)
8. Truncation: Cap to user-supplied `--max` (default 100). Future balancing across thematic buckets can be layered on.

### Output Schema
Each line in `insights_raw.jsonl`:
```json
{
  "sourceUrl": "https://docs.eigenlayer.xyz/restaking/overview",
  "section": "restaking",
  "text": "EigenLayer allows ETH to be restaked, extending security to new protocols.",
  "evidence": [
    "EigenLayer allows ETH to be restaked.",
    "Extending security to new protocols."
  ]
}
```

`section` is inferred as the first path segment after the domain (or `root`).

### CLI Usage
```bash
python src/cli/insights.py scraped_pages.jsonl insights_raw.jsonl --min 50 --max 100
```
Emits a small JSON stats object, e.g.:
```json
{
  "raw_candidates": 732,
  "deduped": 128,
  "written": 100
}
```

### Tests Added
- `test_insight_split.py` – cleaning, splitting, merge heuristic sanity.
- `test_insight_filter_dedupe.py` – end-to-end extract + dedupe and fluff filtering.

### Future Enhancements
| Area | Next Step |
|------|-----------|
| Fuzzy dedupe | MinHash / Jaccard > 0.9 removal |
| Category balancing | Track counts per thematic bucket; re-rank |
| Proper noun detection | NER pass (spaCy) or capitalized token pattern |
| Metric normalization | Parse % / numbers into structured fields |
| Risk tagging | Classifier for risk vs neutral tone |
| Evidence robustness | Store char spans in original text |

---
Next natural step: add category tagging + fuzzy dedupe to refine insight quality.

---
## Classification Strategies (Hybrid, Low / No Label)

The project now supports a layered classification approach optimized for early phases without human gold labels.

### 1. Heuristic Layer (Baseline)
Deterministic regex + keyword patterns produce an initial label, tag (taxonomy v2), signals, and a `ruleStrength` score (0–1). High-signal risk terms (e.g. slashing, exploit) score 1.0.

### 2. Self-Training Layer (Pseudo-Label Model)
Trains a multinomial Logistic Regression on TF‑IDF features using only high-confidence heuristic outputs (filter by `--minRuleStrength`). Produces fast probabilistic predictions and can be temperature calibrated.

Train:
```bash
python src/cli/self_train.py \
  --in data/eigenlayer.insights.enriched.jsonl \
  --out models/selftrain \
  --minRuleStrength 0.5 \
  --calibrate
```

Artifacts written:
```
models/selftrain/
  model.pkl            # LogisticRegression
  vectorizer.pkl       # TF-IDF vocabulary
  metadata.json        # taxonomyVersion, thresholds, counts
  calibration.json     # (optional) temperature + ECE
```

### 3. Zero-Shot NLI Fallback (Optional)
For low-confidence cases, a zero-shot entailment model (e.g. `facebook/bart-large-mnli`) can re-score Risk / Advantage / Neutral hypotheses. This requires `transformers` installed; if absent, a stub returns Neutral.

Install (optional):
```bash
pip install transformers torch --upgrade
```

### 4. Ensemble Routing
Decision flow:
1. Heuristic classify → if `ruleStrength >= ruleStrongThreshold` accept.
2. Else self-train model prediction.
3. If model top probability < `modelFloor` OR (predicted Neutral & weak ruleStrength) and zero-shot enabled → run NLI fallback.

CLI:
```bash
python src/cli/ensemble_classify.py \
  --in data/eigenlayer.insights.enriched.jsonl \
  --out out/ensemble.labeled.jsonl \
  --model models/selftrain \
  --ruleStrong 0.75 \
  --modelFloor 0.55 \
  --enableZeroShot
```

Output augmentation fields:
| Field | Description |
|-------|-------------|
| label | Final top-level label (Risk/Advantage/Neutral) |
| tag | Sub-tag (taxonomy v2) |
| strategy | 'heuristic' or 'ensemble' |
| ruleStrength | Heuristic confidence proxy (0–1) |
| signals | Matched heuristic signal tokens |
| modelProbs | Probability dict from self-train model (if used) |
| nli | Zero-shot scores + model name (if fallback executed) |
| classificationProvenance | Ordered list of stages executed |

### Configuration Notes
- Adjust thresholds to tune precision/recall trade-offs.
- Lower `--minRuleStrength` during self-train to increase recall; monitor noise.
- Re-train easily after taxonomy updates; artifacts store taxonomy version.

### Future Extensions
- DistilBERT embedding backend (swap TF-IDF) for better semantic generalization.
- Active learning loop: surface high entropy disagreements for manual labeling.
- Advanced calibration (isotonic / Platt) when gold labels become available.

### Confidence & Debug Additions
- `finalConfidence`: Combined max(ruleStrength, modelTopProb) with optional +0.1 bounded NLI agreement boost.
- `--debug --explainTopK K` on `ensemble_classify` adds `topFeatures` (feature:weight pairs) for traceability.

### Active Learning Queue
Generate top uncertain / disagreement samples:
```bash
python src/cli/active_learning_queue.py --in out/ensemble.labeled.v2.jsonl --out out/active_queue.jsonl --top 40
```
Ranking score = entropy(modelProbs) + 0.6*heuristic_disagree + 0.4*nli_disagree.

### Calibration Check
Quick reliability bin summary:
```bash
python src/cli/calibration_check.py --in out/ensemble.labeled.v2.jsonl --field finalConfidence --bins 8
```
Outputs JSON with bin counts and average confidence for monitoring drift.

---
## Environment & Dependencies (Stratified)

`requirements.txt` groups packages by tier:

| Tier | Purpose | Key Packages |
|------|---------|--------------|
| Core | Crawl + extract + heuristic & TF-IDF self-train | requests, beautifulsoup4, lxml, numpy, tqdm, scikit-learn |
| Advanced | Embeddings + zero-shot NLI | sentence-transformers, torch, transformers |
| Optional | Data analysis | pandas |
| Dev | Testing / formatting | pytest, black |

Install core only:
```bash
pip install requests beautifulsoup4 lxml tqdm numpy scikit-learn
```

Full stack:
```bash
pip install -r requirements.txt
```

Environment verification:
```bash
python scripts/env_check.py
```
If `activeVenv` is `UNKNOWN`, re-activate (PowerShell):
```powershell
 .\.venv\Scripts\Activate
```

## Classification Modes (Planned Unified CLI)
| Mode | Layers | Added Deps |
|------|--------|-----------|
| minimal | heuristic (+ TF-IDF self-train) | (core) |
| semantic | + SBERT embeddings | sentence-transformers, torch |
| full | + zero-shot fallback | transformers |

Planned unified config (JSON):
```jsonc
{
  "enableSelfTrain": true,
  "enableEmbeddings": false,
  "enableZeroShot": false,
  "strongRuleThreshold": 0.75,
  "modelFloor": 0.55,
  "rationaleMode": "template"
}
```

Minimal classification (current simple CLI):
```bash
python src/cli/classify_v2.py \
  --in data/eigenlayer.insights.enriched.jsonl \
  --out out/insights_classified.jsonl \
  --model models/selftrain_embed
```

Ensemble (advanced legacy):
```bash
python src/cli/ensemble_classify.py \
  --in data/eigenlayer.insights.enriched.jsonl \
  --model models/selftrain_embed \
  --out out/ensemble.labeled.jsonl \
  --enableZeroShot
```

## Packaging & Installation

Install editable (development):
```powershell
pip install -e .
```
Console scripts provided after install:
```powershell
tribute-run --url https://example.com --all
tribute-validate --workDir out/run_20250101_120301 --strict
tribute-synthetic --out synthetic.jsonl --per-class 30
```
For full (zero-shot + embeddings) dependencies:
```powershell
pip install -e .[full]
```

## Docker Usage

Build image:
```powershell
docker build -t tribute-pipeline .
```
Run end-to-end (auto workdir inside container):
```powershell
docker run --rm -v ${PWD}:/workspace -w /workspace tribute-pipeline \
  python scripts/run_pipeline.py --url https://example.com --all
```
(Outputs appear under `out/` on the host.)

To run with full extras (if not baked in), add after build:
```powershell
docker run --rm tribute-pipeline pip install .[full]
```
Then execute a pipeline command as above.

---
## Labeling Module (Gold Data Workflow)
See `docs/LABELING_MODULE.md` for full details.

Key scripts:
| Script | Purpose |
|--------|---------|
| labeling_prepare.py | Sample raw insights into annotation template |
| labeling_validate.py | Enforce schema + guideline rules |
| labeling_split.py | Stratified split into train/dev/test |
| evaluate_labeled.py | Macro F1, confusion, ECE |
| calibrate_confidence.py | Temperature / isotonic scaling of confidence |

Example flow:
```bash
python scripts/labeling_prepare.py --in insights_raw.jsonl --out data/labeling_batch.v1.jsonl --max 150
# (Annotate externally -> produce data/labeling_batch.v1.labeled.jsonl)
python scripts/labeling_validate.py --in data/labeling_batch.v1.labeled.jsonl --taxonomy-version v1.0-draft
python scripts/labeling_split.py --in data/labeling_batch.v1.labeled.jsonl \
  --train-out data/train.jsonl --dev-out data/dev.jsonl --test-out data/test.jsonl --dev 0.3 --test 0.2
python scripts/evaluate_labeled.py --gold data/test.jsonl --pred out/insights_classified.jsonl
python scripts/calibrate_confidence.py --pred out/insights_classified.jsonl --gold data/dev.jsonl \
  --method temperature --out out/calibration.json
```

---
### Pseudo Labels (Demonstration Only)
`scripts/pseudo_label_generate.py` can fabricate a "pseudo" labeled set by selecting high-confidence model outputs. This is ONLY for workflow testing:
* Inflates apparent performance (selection bias toward confident samples).
* Must never be used to claim real macro F1.
* Replace entirely with human-labeled set before reporting metrics.

Example:
```bash
python scripts/pseudo_label_generate.py --pred out/insights_classified.jsonl --out data/pseudo_gold.jsonl --min-conf 0.8 --per-class 40
python scripts/evaluate_labeled.py --gold data/pseudo_gold.jsonl --pred out/insights_classified.jsonl
```

---
