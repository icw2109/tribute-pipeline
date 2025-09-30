"""Probability calibration scaffold.

Provides small utilities to fit a calibration layer on top of existing
backend probability outputs. Real calibration will require a held-out
validation set. For now we implement lightweight Platt scaling and an
isotonic placeholder (delegating to scikit-learn if available) while keeping
the interface minimal and deferrable.

Intended future usage:
  1. Train backend on train split.
  2. Collect raw predicted probabilities on dev split.
  3. Fit calibrator per class (one-vs-rest) or temperature scaling.
  4. Wrap backend.predict_proba to apply calibration params.

We start with a temperature scaling (single scalar) variant + per-class
Platt logistic parameters for flexibility. Both are optional.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Sequence
import math

try:  # optional dependency usage
    from sklearn.isotonic import IsotonicRegression  # type: ignore
    _HAS_ISO = True
except Exception:  # pragma: no cover - absence path
    _HAS_ISO = False


@dataclass
class TemperatureCalibrator:
    temperature: float = 1.0

    def apply(self, probs: List[Dict[str, float]]):
        if abs(self.temperature - 1.0) < 1e-6:
            return probs
        out: List[Dict[str, float]] = []
        for row in probs:
            # convert to logits, divide by T, softmax back
            labs = list(row.keys())
            vals = [row[l] for l in labs]
            # guard numerical stability
            eps = 1e-12
            vals = [min(max(v, eps), 1 - eps) for v in vals]
            logits = [math.log(v) - math.log(1 - v) for v in vals]
            scaled = [lg / self.temperature for lg in logits]
            m = max(scaled)
            exps = [math.exp(s - m) for s in scaled]
            z = sum(exps)
            new_row = {labs[i]: exps[i] / z for i in range(len(labs))}
            out.append(new_row)
        return out


@dataclass
class PlattCalibrator:
    # per-label (A,B) sigmoid params so calibrated_prob = 1/(1+exp(A*x + B))
    params: Dict[str, tuple[float, float]]

    def apply(self, probs: List[Dict[str, float]]):
        out: List[Dict[str, float]] = []
        for row in probs:
            new_row = {}
            for lab, p in row.items():
                A, B = self.params.get(lab, (0.0, 0.0))
                # invert to logit domain, then apply linear, then sigmoid
                eps = 1e-12
                p = min(max(p, eps), 1 - eps)
                logit = math.log(p) - math.log(1 - p)
                z = 1 / (1 + math.exp(A * logit + B))
                new_row[lab] = z
            # renormalize to sum 1
            s = sum(new_row.values()) or 1.0
            for k in list(new_row.keys()):
                new_row[k] = new_row[k] / s
            out.append(new_row)
        return out


@dataclass
class IsotonicCalibrator:
    # per-label isotonic regression objects
    models: Dict[str, Any]  # type: ignore

    def apply(self, probs: List[Dict[str, float]]):  # pragma: no cover - simple path
        out: List[Dict[str, float]] = []
        for row in probs:
            new_row = {}
            for lab, p in row.items():
                model = self.models.get(lab)
                if model is None:
                    new_row[lab] = p
                else:
                    new_row[lab] = float(model.predict([p])[0])
            s = sum(new_row.values()) or 1.0
            for k in list(new_row.keys()):
                new_row[k] /= s
            out.append(new_row)
        return out


def _apply_temp_row(row: Dict[str, float], T: float) -> Dict[str, float]:
    # Convert probs to logits and scale then softmax
    import math as _m
    eps = 1e-12
    labs = list(row.keys())
    vals = [min(max(row[l], eps), 1 - eps) for l in labs]
    logits = [_m.log(v) - _m.log(1 - v) for v in vals]
    scaled = [lg / T for lg in logits]
    m = max(scaled)
    exps = [_m.exp(s - m) for s in scaled]
    z = sum(exps) or 1.0
    return {labs[i]: exps[i] / z for i in range(len(labs))}

def _nll(probs: Sequence[Dict[str,float]], labels: Sequence[str]) -> float:
    import math as _m
    s = 0.0
    for row, lab in zip(probs, labels):
        p = row.get(lab, 1e-12)
        p = min(max(p, 1e-12), 1 - 1e-12)
        s += -_m.log(p)
    return s / max(len(probs),1)

def fit_temperature(probs: Sequence[Dict[str, float]], labels: Sequence[str]):  # pragma: no cover (logic simple)
    """Optimize a single temperature to minimize NLL on provided dev set.

    We assume multi-class probabilities that sum to 1. We treat given probs
    as already softmax outputs; convert to logits via log(p)-log(1-p) which
    is an approximation for multi-class but adequate for scaling monotonicity.
    A coarse grid search followed by fine search around the best value keeps
    implementation dependency-free.
    """
    if not probs:
        return TemperatureCalibrator(temperature=1.0)
    coarse = [0.5,0.75,1.0,1.25,1.5,2.0,2.5,3.0,4.0,5.0]
    best_T = 1.0
    best_loss = float('inf')
    for T in coarse:
        scaled = [_apply_temp_row(r, T) for r in probs]
        loss = _nll(scaled, labels)
        if loss < best_loss:
            best_loss = loss; best_T = T
    # Fine search around best
    low = max(0.1, best_T * 0.5); high = best_T * 1.5
    step = (high - low) / 40.0
    cur = low
    while cur <= high:
        scaled = [_apply_temp_row(r, cur) for r in probs]
        loss = _nll(scaled, labels)
        if loss < best_loss:
            best_loss = loss; best_T = cur
        cur += step
    return TemperatureCalibrator(temperature=round(best_T,4))


def fit_platt(probs: Sequence[Dict[str, float]], labels: Sequence[str]):  # pragma: no cover placeholder
    # Placeholder: returns neutral params (identity)
    return PlattCalibrator(params={})


def fit_isotonic(probs: Sequence[Dict[str, float]], labels: Sequence[str]):  # pragma: no cover placeholder
    if not _HAS_ISO:
        raise RuntimeError("scikit-learn isotonic regression not available")
    # Placeholder: no fitting yet
    return IsotonicCalibrator(models={})


__all__ = [
    'TemperatureCalibrator','PlattCalibrator','IsotonicCalibrator',
    'fit_temperature','fit_platt','fit_isotonic'
]
