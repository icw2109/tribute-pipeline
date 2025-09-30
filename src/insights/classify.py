from __future__ import annotations
"""Rule-based classification for investor insight sentences.

Categories:
  - Risk: security or downside / uncertainty related.
  - Advantage: growth, traction, differentiation, performance.
  - Neutral: none of the above patterns.

Heuristics are intentionally transparent & deterministic. A future ML model can
replace classify() with same return contract.
"""
from dataclasses import dataclass
from typing import List, Tuple, Dict
import re

# Token lists kept lowercase; matching done on lowercased text
RISK_TERMS = {
    'risk','risks','slashing','slashed','penalty','penalties','penalized','exploit','exploits','vulnerability','attack','attacks','downtime','loss','uncertainty','regulatory','liability','slash'
    # note: 'audit','audited' moved to a separate weak-risk bucket
}
WEAK_RISK_TERMS = {'audit','audited','bug','bugs'}
ADVANTAGE_TERMS = {
    'growth','increase','increased','increasing','scaling','scalable','partnership','partnerships','integration','integrations','adoption','adopted','launch','launched','innovative','efficiency','efficient','performance','improvement','improved','unique','differentiated','restaking','throughput','scalability','expansion','expanded','expanding','milestone'
}
NEGATION_TERMS = {'no','not','without','never'}  # simplistic

PERCENT_PATTERN = re.compile(r"\b\d{1,3}(?:\.\d+)?%\b")
NUMBER_PATTERN = re.compile(r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b")

@dataclass
class ClassificationResult:
    label: str
    signals: List[str]


def _collect_signals(text: str, vocab: set[str]) -> List[str]:
    tl = text.lower()
    found = []
    for term in vocab:
        if term in tl:
            found.append(term)
    return sorted(found)


def classify(text: str) -> ClassificationResult:
    """Classify text into Advantage / Risk / Neutral.

    Precedence: Risk > Advantage > Neutral. This ensures risk language isn't
    overshadowed by positive framing.
    """
    tl = text.lower()
    risk_hits = _collect_signals(tl, RISK_TERMS)
    weak_risk_hits = _collect_signals(tl, WEAK_RISK_TERMS)
    adv_hits = _collect_signals(tl, ADVANTAGE_TERMS)

    # Numeric / percent emphasis can upgrade Advantage if positive context present
    numeric = bool(PERCENT_PATTERN.search(text) or NUMBER_PATTERN.search(text))

    # Simple negation check: if risk word appears within a small window of a negation, drop it
    # (e.g., "no security risk")
    def negated(term: str) -> bool:
        idx = tl.find(term)
        if idx == -1:
            return False
        # window tokens before term
        window = re.findall(r"\w+", tl[max(0, idx-20):idx])
        return any(tok in NEGATION_TERMS for tok in window[-3:])

    filtered_risk = [t for t in risk_hits if not negated(t)]

    if filtered_risk:
        return ClassificationResult('Risk', filtered_risk)

    # weak risk terms only count if at least one non-negated strong risk also present
    filtered_weak = [t for t in weak_risk_hits if not negated(t)]
    if filtered_weak and adv_hits == []:  # treat as Neutral if co-occurs with growth (audit passed context)
        # choose Neutral unless explicitly wanted; here we downgrade to Neutral (no return)
        pass

    if adv_hits or (numeric and adv_hits):  # numeric currently not changing logic; placeholder for weighting
        return ClassificationResult('Advantage', adv_hits or ([] if not numeric else ['numeric']))

    return ClassificationResult('Neutral', [])

__all__ = ['classify','ClassificationResult']
