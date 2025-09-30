from __future__ import annotations
"""Inference utilities for self-trained pseudo-label classifier."""
import json
from pathlib import Path
from typing import List, Dict, Any
import joblib
import numpy as np

class SelfTrainModel:
    def __init__(self, model_path: str):
        base = Path(model_path)
        self.clf = joblib.load(base / 'model.pkl')
        self.vec = joblib.load(base / 'vectorizer.pkl')
        meta_path = base / 'metadata.json'
        self.meta = json.loads(meta_path.read_text(encoding='utf-8')) if meta_path.exists() else {}
        # Expected (full) label set from metadata
        self.labels = self.meta.get('labelSet') or ['Risk','Advantage','Neutral']
        # Actual labels present in trained classifier (subset possible)
        self.model_labels = list(getattr(self.clf, 'classes_', self.labels))
        calib_path = base / 'calibration.json'
        self.temperature = None
        if calib_path.exists():
            try:
                c = json.loads(calib_path.read_text(encoding='utf-8'))
                self.temperature = c.get('temperature')
            except Exception:
                pass

    def predict(self, texts: List[str]) -> List[Dict[str,Any]]:
        X = self.vec.transform(texts)
        raw = self.clf.predict_proba(X)
        # Expand to full label set if needed
        full = []
        for row in raw:
            full_vec = np.zeros(len(self.labels), dtype=float)
            for i, lab in enumerate(self.model_labels):
                try:
                    idx = self.labels.index(lab)
                    full_vec[idx] = row[i]
                except ValueError:
                    continue
            full.append(full_vec)
        probs = np.vstack(full)
        if self.temperature:
            probs = probs / self.temperature
        # Renormalize
        denom = probs.sum(axis=1, keepdims=True)
        denom[denom == 0] = 1.0
        probs = probs / denom
        results = []
        for row in probs:
            top_idx = int(np.argmax(row))
            results.append({
                'label': self.labels[top_idx],
                'probs': {self.labels[j]: float(row[j]) for j in range(len(self.labels))}
            })
        return results

    def explain_top_features(self, text: str, top_k: int = 5) -> List[str]:
        # For multinomial logistic regression: use difference between class weights
        try:
            vec = self.vec.transform([text])
            if not hasattr(self.clf, 'coef_'):
                return []
            # pick predicted class
            probs = self.clf.predict_proba(vec)[0]
            cls_idx = int(np.argmax(probs))
            coefs = self.clf.coef_[cls_idx]
            # map indices to feature names
            feats = np.array(self.vec.get_feature_names_out())
            # Multiply by feature values (sparse -> toarray)
            vals = vec.toarray()[0]
            contrib = coefs * vals
            top_ids = np.argsort(-contrib)[:top_k]
            out = []
            for tid in top_ids:
                if vals[tid] > 0:
                    out.append(f"{feats[tid]}:{contrib[tid]:.3f}")
            return out
        except Exception:
            return []

__all__ = ["SelfTrainModel"]
