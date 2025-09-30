# Evaluation Plan

## Objectives
Validate classification performance (Advantage | Risk | Neutral) targeting macro F1 ≥ 0.70 with balanced class recall and calibrated confidence.

## Data Collection
1. Sample 150 raw extracted insights (ensuring diversity of sources and sections).
2. Curate 90 labeled examples (30 per class target). If class scarcity occurs, oversample candidate sentences with heuristic signals pointing to underrepresented classes.
3. Reserve 30 as a frozen test set; 60 for development.
4. Record `taxonomyVersion`, annotator initials, and any ambiguity notes.

## Annotation Guidelines
See `LABELING_GUIDELINES.md`.
- Enforce atomicity: split multi-claim sentences.
- Remove (not label) pure marketing fluff with no factual claim.

## Metrics
- Macro precision / recall / F1.
- Per-class support & confusion matrix.
- Expected Calibration Error (ECE) with 10 bins.
- Neutral Ratio (health check) expected 0.2–0.5 for balanced corpora.
- Mean cluster entropy (k=8 hashed embedding KMeans) < 1.25 recommended.

## Procedure
1. Run classifier on test set to produce predictions.
2. Execute: `python scripts/evaluate_labeled.py --gold data/labeled_test.jsonl --pred out/insights_classified.jsonl`.
3. If macro F1 < 0.70 or any class recall < 0.55:
   - Adjust heuristic thresholds or swap 1–2 few-shot exemplars (if LLM path adopted later).
   - Re-run only on dev set. Keep test set untouched.
4. If ECE > 0.12, perform temperature scaling on dev predictions and re-score test predictions.

## Calibration (Optional Step)
1. Fit temperature T minimizing NLL on dev predictions (self-train logits or approximate via inverse of Platt if only probabilities).
2. Apply scaling and re-run ECE.
3. Store method + T in future `run_manifest.json` under `calibration` key.

## Drift Monitoring (Future)
For subsequent runs, track trends in:
- Neutral ratio
- Mean entropy
- Label distribution
- ECE
Trigger manual review if any metric deviates >20% relative from baseline.

## Acceptance Criteria
| Metric | Threshold |
|--------|-----------|
| Macro F1 | ≥ 0.70 |
| Per-class recall | ≥ 0.55 |
| ECE | ≤ 0.12 |
| Neutral ratio | 0.2–0.5 |
| Mean entropy (k=8) | < 1.25 |

## Known Risks
- Small test size may yield variance; consider expanding after first iteration.
- Heuristic bias in seed labeling; mitigate via uncertainty sampling in later rounds.
- Overfitting to dev through excessive prompt / threshold changes (limit to two iterations before freezing).
