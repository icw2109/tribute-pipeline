"""Feature extraction layer for hybrid classification.

Produces a deterministic feature dictionary for each insight. This layer is
kept separate so it can be unit tested without invoking any ML code.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, List
import re

from .lexicon import Lexicon, DEFAULT_LEXICON


RATIO_PATTERN = re.compile(r"\b\d+(?:\.\d+)?x\b")
PERCENT_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d+)?%\b")
NUMBER_PATTERN = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b")


@dataclass
class FeatureResult:
    features: Dict[str, Any]
    trace: Dict[str, Any]


def _token_lower_list(text: str) -> List[str]:
    return re.findall(r"[a-zA-Z0-9']+", text.lower())


def extract_features(text: str, lexicon: Lexicon = DEFAULT_LEXICON) -> FeatureResult:
    tl_tokens = _token_lower_list(text)
    tl_text = " ".join(tl_tokens)

    def present_any(terms):
        hits = [t for t in terms if t in tl_text]
        return hits

    risk_hits = present_any(lexicon.risk_terms)
    weak_risk_hits = present_any(lexicon.weak_risk_terms)
    adv_hits = present_any(lexicon.advantage_terms)
    comparative_hits = present_any(lexicon.comparative_terms)
    perf_hits = present_any(lexicon.performance_terms)
    partner_hits = present_any(lexicon.partner_terms)

    # Negation heuristics: look back 3 tokens from each advantage / risk token start
    negations = []
    negated_adv = False
    negated_risk = False
    for idx, tok in enumerate(tl_tokens):
        if tok in lexicon.negation_terms:
            negations.append(idx)

    def _is_negated(target_hits):
        for h in target_hits:
            # locate first index occurrence of term (approximate)
            parts = h.split()
            for i, tok in enumerate(tl_tokens):
                if tok == parts[0]:
                    # window of preceding 3 tokens
                    for n in negations:
                        if 0 <= n < i and i - n <= 3:
                            return True
        return False

    if adv_hits:
        negated_adv = _is_negated(adv_hits)
    if risk_hits:
        negated_risk = _is_negated(risk_hits)

    ratio_hits = RATIO_PATTERN.findall(text)
    percent_hits = PERCENT_PATTERN.findall(text)
    number_hits = NUMBER_PATTERN.findall(text)

    numeric_context = bool(ratio_hits or percent_hits or number_hits)

    features: Dict[str, Any] = {
        "len_chars": len(text),
        "len_tokens": len(tl_tokens),
        "risk_count": len(risk_hits),
        "weak_risk_count": len(weak_risk_hits),
        "adv_count": len(adv_hits),
        "comparative_count": len(comparative_hits),
        "performance_count": len(perf_hits),
        "partner_count": len(partner_hits),
        "has_numeric": numeric_context,
        "ratio_count": len(ratio_hits),
        "percent_count": len(percent_hits),
        "number_count": len(number_hits),
        "negated_advantage": negated_adv,
        "negated_risk": negated_risk,
        "lexicon_hash": lexicon.hash(),
        "lexicon_version": lexicon.version,
    }

    trace: Dict[str, Any] = {
        "risk_terms": risk_hits,
        "weak_risk_terms": weak_risk_hits,
        "advantage_terms": adv_hits,
        "comparative_terms": comparative_hits,
        "performance_terms": perf_hits,
        "partner_terms": partner_hits,
        "ratio_patterns": ratio_hits,
        "percent_patterns": percent_hits,
        "number_patterns": number_hits,
        "negation_indices": negations,
        "negated_advantage": negated_adv,
        "negated_risk": negated_risk,
    }

    return FeatureResult(features=features, trace=trace)


__all__ = ["extract_features","FeatureResult"]
