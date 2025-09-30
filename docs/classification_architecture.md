## Classification Architecture

Goal: Produce for each insight:
```
{
  "text": ..., 
  "label": "Advantage|Risk|Neutral",
  "labelTag": "Subcategory",
  "rationale": "Short explanation",
  "confidence": 0.0-1.0
}
```

### Layered Stack (Configurable)
1. Heuristic Layer (always on)
   - Pattern / keyword rules -> (label, tag, signals, ruleStrength)
2. Self-Train Layer (optional)
   - LogisticRegression trained on high-confidence heuristic pseudo-labels
   - Vectorization backend: TF-IDF (default) or SBERT embeddings
3. Zero-Shot NLI Layer (optional)
   - HuggingFace zero-shot classification for fallback / disagreement cases
4. Post-Processing
   - Confidence fusion = max(ruleStrength, modelTopProb) (+ optional bounded NLI boost)
   - Rationale templating referencing signals/tag & evidence type

### Configuration Model (Planned)
```
{
  "enableSelfTrain": true,
  "enableEmbeddings": false,
  "enableZeroShot": false,
  "strongRuleThreshold": 0.75,
  "modelFloor": 0.55,
  "rationaleMode": "template"
}
```

### Component Contracts
| Component | Input | Output | Notes |
|-----------|-------|--------|-------|
| HeuristicClassifier | text | {label, tag, signals, ruleStrength} | Deterministic, fast |
| Vectorizer | texts | matrix/embeddings | TF-IDF or SBERT |
| SelfTrainModel | text | {label, probs{}} | Pseudo-labeled logistic regression |
| ZeroShotAdapter | text | {label, scores{}, available} | Wrapped HF pipeline |
| Fusion | heur + model + nli | final label, confidence | Chooses highest confidence |
| RationaleBuilder | text + meta | rationale string | ≤180 chars deterministic |

### Extension Paths
| Extension | Hook Point | Approach |
|-----------|-----------|----------|
| Few-shot Prompt | Replace / augment SelfTrainModel | Use small instruct model via API; convert examples into in-context prompt |
| LoRA / PEFT Fine-tune | New adapter implementing model.predict | Train lightweight head on domain data, preserve contract |
| Calibration (Isotonic) | Fusion stage post model probs | Apply after gold labels available |
| Active Learning | Sample selection pre self-train retrain | Entropy & disagreement queue |
| Embedding Upgrade | Vectorizer | Swap SBERT for better model (e5, Instructor) |
| Rationale LLM | RationaleBuilder | Backfill natural language reasons conditioned on label + snippet |

### Minimal vs Full Pipeline
| Mode | Layers | Dependencies |
|------|--------|--------------|
| minimal | heuristic (+optional self-train TF-IDF) | Core only |
| semantic | + self-train SBERT | + sentence-transformers, torch |
| full | + zero-shot | + transformers |

### Reliability & Confidence
- Early stage: heuristic ruleStrength correlates with precision for Risk.
- Self-train adds recall for Advantage/Neutral boundary.
- Zero-shot fallback raises robustness on out-of-vocabulary phrasing.
- Future: reliability diagram + ECE once gold labels exist.

### Rationale Strategy
Heuristic/template rationale is intentionally deterministic:
`"Risk due to signals: slashing, penalty; strong rule match."`

Future enhancement: LLM rationale generator gated behind `--enableRationaleLLM`.

### Testing Strategy
| Test | Purpose |
|------|---------|
| test_heuristic_labels | Ensure deterministic mapping for canonical phrases |
| test_self_train_roundtrip | Train → save → load → predict consistency |
| test_zero_shot_stub | Works when transformers missing |
| test_pipeline_modes | minimal vs full produce valid schema |

### Migration Plan
1. Introduce `classifier_config.json`.
2. Add unified `classifier_pipeline.py` orchestrator.
3. Deprecate legacy multi-CLI in docs; keep for backward compatibility short term.
4. Add smoke tests for each mode.
5. (Optional) Add few-shot prompt adapter skeleton.

### Few-Shot Adapter (Sketch)
```
class FewShotPromptAdapter:
    def __init__(self, model_client, examples): ...
    def predict(self, text: str):
        # returns {label, probs}
```

### LoRA Adapter (Sketch)
```
class LoraAdapter:
    def __init__(self, model_path, peft_weights): ...
    def predict(self, texts: List[str]): ...
```

Both conform to the same `predict` signature allowing drop-in fusion.

### Open Questions
1. Desired target distribution balance? (Currently Neutral heavy.)
2. How to treat multi-label edge cases (hybrid Advantage + Risk sentence)?
3. Confidence calibration tolerance (±0.05 ECE acceptable?)

---
This document will evolve as we consolidate the unified pipeline implementation.
