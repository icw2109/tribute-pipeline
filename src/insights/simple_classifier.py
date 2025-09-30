"""Simplified Part 3 classification pipeline.

Produces required output fields only: label, labelTag, rationale, confidence.

Strategy:
 1. Run heuristic rules (existing heuristic_classify) -> base label, tag, ruleStrength, signals.
 2. If self-train model provided AND ruleStrength below threshold, get model probabilities.
 3. Fuse confidence = max(ruleStrength, model_top_prob) (bounded [0,1]).
 4. Generate rationale using lightweight template referencing signals & tag.

This keeps surface minimal while allowing an incremental learning hook.
"""
from __future__ import annotations
from typing import Optional, Dict, Any, List

from .heuristic import heuristic_classify
try:
    from .self_train_infer import SelfTrainModel
except Exception:  # pragma: no cover
    SelfTrainModel = None  # type: ignore

DEFAULT_STRONG = 0.75

def _truncate(txt: str, n: int) -> str:
    return txt if len(txt) <= n else txt[:n-1].rstrip() + '…'

def build_rationale(text: str, label: str, tag: str, signals: List[str], rule_strength: float, model_prob: Optional[float]) -> str:
    # Prioritize signals
    if signals:
        sig_part = ', '.join(signals[:3])
    else:
        sig_part = tag.lower() if tag else label.lower()
    evid = f"signals: {sig_part}" if signals else f"pattern match for {sig_part}"
    conf_phrase = None
    if model_prob is not None and model_prob >= rule_strength:
        conf_phrase = "model agreement"
    elif rule_strength >= 0.75:
        conf_phrase = "strong rule match"
    else:
        conf_phrase = "heuristic pattern"
    rationale = f"{label} due to {evid}; {conf_phrase}.".strip()
    return _truncate(rationale, 180)

class SimpleClassifier:
    def __init__(self, self_train_model_path: Optional[str] = None, strong_threshold: float = DEFAULT_STRONG):
        self.model = None
        if self_train_model_path:
            try:
                self.model = SelfTrainModel(self_train_model_path)  # type: ignore
            except Exception:
                self.model = None
        self.strong_threshold = strong_threshold

    def classify(self, text: str) -> Dict[str, Any]:
        heur = heuristic_classify(text)
        label = heur['label']
        tag = heur.get('tag') or ''
        rule_strength = heur.get('ruleStrength', 0.0)
        signals = heur.get('signals', [])
        model_prob = None
        if self.model and rule_strength < self.strong_threshold:
            pred = self.model.predict([text])[0]
            label = pred['label']  # allow override when heuristic weak
            model_prob = max(pred['probs'].values()) if pred.get('probs') else None
        confidence = max([c for c in [rule_strength, model_prob] if c is not None] or [rule_strength])
        rationale = build_rationale(text, label, tag, signals, rule_strength, model_prob)
        return {
            'label': label,
            'labelTag': tag,
            'rationale': rationale,
            'confidence': round(confidence, 3)
        }

__all__ = ["SimpleClassifier"]