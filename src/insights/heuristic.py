"""Unified heuristic classification wrapper.

Combines:
  * Basic risk/advantage/neutral label from `classify.classify`
  * Tag inference from `tag_inference.infer_with_validation`
  * Rule strength scoring for routing (used by ensemble strategy)

Rule Strength Heuristic:
  - Count of unique signal terms (from classify result) + tag pattern hits
  - Boost for high-signal risk terms (slashing/exploit) to 1.0 cap
  - Normalized to [0,1]

Exports:
  heuristic_classify(text) -> dict with keys:
    label, tag, signals, ruleStrength, rationale
"""
from __future__ import annotations
from typing import Dict, List
import re
from .classify import classify
from .tag_inference import infer_with_validation

HIGH_SIGNAL_RISK = {"slashing","exploit","attack","slash","vulnerab"}


def _score(signals: List[str]) -> float:
    if not signals:
        return 0.0
    if any(s in HIGH_SIGNAL_RISK for s in signals):
        return 1.0
    # simple logarithmic-ish dampening
    raw = len(set(signals)) / 5.0
    if raw > 1.0:
        raw = 1.0
    return round(raw,3)


DECLINE_PATTERN = re.compile(r"(?:(?:declin|decreas|down|drop|fell|lower|reduc)(?:ed|es|ing)?).{0,40}?\b(\d{1,3}(?:\.\d+)?%?)\b", re.IGNORECASE)
NEG_GROWTH_PATTERN = re.compile(r"\b(-\d{1,3}(?:\.\d+)?%?)\b")

def _detect_decline(text: str) -> bool:
    if DECLINE_PATTERN.search(text):
        return True
    if NEG_GROWTH_PATTERN.search(text):
        return True
    return False

def heuristic_classify(text: str) -> Dict:
    base = classify(text)
    tag_inf = infer_with_validation(text)
    signals = sorted(set(base.signals + tag_inf.signals))
    strength = _score(signals)
    rationale = []
    if base.signals:
        rationale.append(f"base_signals={','.join(base.signals)}")
    if tag_inf.signals:
        rationale.append(f"tag_signals={','.join(tag_inf.signals)}")
    # precedence ensures Risk not downgraded accidentally
    final_label = tag_inf.label if tag_inf.label != base.label and tag_inf.label == 'Risk' else base.label
    final_tag = tag_inf.tag
    if final_label != 'Risk' and _detect_decline(text):
        # upgrade to Risk (Execution or Economic risk depending on context tokens)
        ctx = text.lower()
        if any(k in ctx for k in ['revenue','sales','tv','tvl','volume','users','retention','stake','deposit']):
            final_tag = 'Economic Risk'
        else:
            final_tag = 'Execution Risk'
        final_label = 'Risk'
        signals.append('decline_metric')
        strength = min(1.0, strength + 0.2)
        rationale.append('decline_metric')
    return {
        "label": final_label,
        "tag": final_tag,
        "signals": sorted(set(signals)),
        "ruleStrength": round(strength,3),
        "rationale": "; ".join(rationale)
    }

__all__ = ["heuristic_classify"]
