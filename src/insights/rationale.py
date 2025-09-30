from __future__ import annotations
"""Rationale generation utility.

Deterministic, concise template citing signals (if any) or tag and
describing which evidence source contributed most to confidence.
"""
from typing import List, Optional

def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"

def build_rationale(
    label: str,
    tag: str,
    signals: List[str],
    rule_strength: float,
    model_prob: Optional[float] = None,
    nli_supported: bool = False,
    limit: int = 180,
    primary_nli: bool = False,
) -> str:
    if signals:
        evid = "signals: " + ", ".join(signals[:3])
    else:
        evid = f"pattern: {tag.lower() or label.lower()}"
    if primary_nli and nli_supported:
        conf = "nli primary"
    elif model_prob is not None and model_prob >= rule_strength:
        conf = "model agreement"
    elif rule_strength >= 0.75:
        conf = "strong rule match"
    else:
        conf = "heuristic pattern"
    if nli_supported:
        conf += ", nli support"
    rationale = f"{label} due to {evid}; {conf}."
    # Enforce word cap (25 words) after initial assembly, before char truncation
    words = rationale.split()
    if len(words) > 25:
        rationale = " ".join(words[:25]) + "…"
    return _truncate(rationale, limit)

__all__ = ["build_rationale"]

