from __future__ import annotations
"""Zero-shot NLI fallback classification.

Uses a transformers pipeline (bart-large-mnli or roberta-large-mnli) if available.
If transformers is not installed, returns a stub indicating unavailability.
"""
from typing import Dict, Any

_LABELS = ["Risk","Advantage","Neutral"]

try:  # lazy import
    from transformers import pipeline
    _pipe = None
    def _load(model_name: str):
        global _pipe
        if _pipe is None:
            _pipe = pipeline("zero-shot-classification", model=model_name)
        return _pipe

    def zero_shot_classify(text: str, model_name: str = "facebook/bart-large-mnli") -> Dict[str,Any]:
        pipe = _load(model_name)
        res = pipe(text, _LABELS, multi_label=False)
        # res: {'sequence':..., 'labels':[...], 'scores':[...]} sorted by score desc
        scores = dict(zip(res['labels'], res['scores']))
        top = res['labels'][0]
        return {
            'label': top,
            'scores': scores,
            'model': model_name,
            'available': True
        }
except Exception:  # transformers not installed
    def zero_shot_classify(text: str, model_name: str = "facebook/bart-large-mnli") -> Dict[str,Any]:  # type: ignore
        return {
            'label': 'Neutral',
            'scores': {l: 0.33 for l in _LABELS},
            'model': model_name,
            'available': False,
            'error': 'transformers_not_available'
        }

__all__ = ["zero_shot_classify"]
