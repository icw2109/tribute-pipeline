# Labeling Module

This module introduces a lightweight, reproducible workflow to collect gold labels for Advantage | Risk | Neutral classification and enable macro F1 + calibration.

## Overview
Scripts:
| Script | Purpose |
|--------|---------|
| `labeling_prepare.py` | Sample raw insights into an annotation-ready JSONL template. |
| `labeling_validate.py` | Validate annotated file against schema and constraints. |
| `labeling_split.py` | Stratified split of labeled set into train/dev/test. |
| `evaluate_labeled.py` | Compute macro F1, per-class metrics, confusion, ECE. |
| `calibrate_confidence.py` | Apply temperature or isotonic scaling to confidence values (dev set). |

## Annotation Schema Fields
| Field | Description |
|-------|-------------|
| id | Integer identifier (local to batch) |
| text | Insight text (atomic) |
| label | Advantage | Risk | Neutral (post-annotation) |
| sourceUrl | Original source page URL |
| candidateType | Heuristic bucket (risk, advantage, tokenomics, adoption, other) |
| qualityScore | Heuristic quality score (0–1) |
| provenance | Data origin (scraped, weak, synthetic, etc.) |
| sample_phase | seed | uncertainty | diversity |
| annotator | Initials of annotator |
| taxonomyVersion | Taxonomy version used |
| rationale_gold | Optional free-text human rationale |
| notes | Optional free-text notes |

## Typical Workflow
1. Prepare batch:  
   `python scripts/labeling_prepare.py --in insights_raw.jsonl --out data/labeling_batch.v1.jsonl --max 150`
2. Distribute file to annotators (ensure consistent taxonomy guidelines).
3. After labeling, validate:  
   `python scripts/labeling_validate.py --in data/labeling_batch.v1.labeled.jsonl --taxonomy-version v1.0-draft`
4. Split:  
   `python scripts/labeling_split.py --in data/labeling_batch.v1.labeled.jsonl --train-out data/train.jsonl --dev-out data/dev.jsonl --test-out data/test.jsonl --dev 0.3 --test 0.2`
5. Classify full corpus, then evaluate on test:  
   `python scripts/evaluate_labeled.py --gold data/test.jsonl --pred out/insights_classified.jsonl`
6. If calibration needed:  
   `python scripts/calibrate_confidence.py --pred out/insights_classified.jsonl --gold data/dev.jsonl --method temperature --out out/calibration.json`
7. (Future) Re-score confidences by applying scaling to raw confidence values before distribution or analytics.

## Calibration Notes
- Temperature scaling assumes a roughly logistic shape; if reliability curve is non-monotonic, prefer isotonic (`--method isotonic`).
- Store calibration parameters, then update downstream systems to apply scaling: `conf' = 1 / (1 + exp(-(logit(conf) / T)))`.

## Quality Tips
- Maintain an annotation changelog for guideline adjustments.
- Avoid reusing the same dev/test split after major taxonomy changes—bump taxonomy version.
- Use `check_health.py` after each new batch to ensure class balance remains acceptable.

## Extensibility
Future enhancements can include active learning batch generation (uncertainty + diversity) and semi-supervised bootstrapping via provisional labels.
