"""Deterministic heuristic mapping from raw text to (label, ADIN tag).

This layer encapsulates precedence + keyword patterns separate from the
legacy simplistic LABEL_TAG_RULES in the classify CLI. It uses ordered
rules so behavior is transparent and easily testable.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import List, Tuple, Dict

from .adin_taxonomy import (
    ADVANTAGE_TAGS,
    RISK_TAGS,
    NEUTRAL_TAGS,
    TopLevel,
    validate,
)

# --- Pattern definitions ---
# Each tuple: (compiled_regex, tag_string)

RISK_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"regulat|compliance|legal|jurisdiction|licen[cs]e", re.I), "Regulatory"),
    (re.compile(r"centraliz|concentrat|single point|multisig", re.I), "Centralization"),
    (re.compile(r"slash|slashing|exploit|attack|vulnerab|bug|incident|breach", re.I), "Security/Slash"),
    (re.compile(r"unlock|emission|inflation|vesting|supply|dilut", re.I), "Token Supply"),
    (re.compile(r"competitor|competition|fragment|alternative|substitut", re.I), "Competition"),
    (re.compile(r"revenue decline|unsustain|shrinking|fee decline|economic risk|runway", re.I), "Economic Risk"),
    (re.compile(r"delay|delayed|behind schedule|slipped|missed milestone|execution risk", re.I), "Execution Risk"),
]

ADVANTAGE_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"adoption|user(s)?|tvl|volume|delegat|traction|growth|retention|cohort", re.I), "Traction"),
    (re.compile(r"partner|partnership|integration|ecosystem|alliance|collaborat", re.I), "Partners"),
    (re.compile(r"audit|audited|formal verification|verified|security review", re.I), "Security/Audit"),
    (re.compile(r"utility|governance token|staking rights|fee burn|restak", re.I), "Token Utility"),
    (re.compile(r"throughput|latency|tps|performance|scalab|cost reduction|efficient|10x|improv|zero-knowledge|zk|encryption", re.I), "Performance"),
    (re.compile(r"team|hired|hiring|founder|lead engineer|researcher|ex-(google|amazon|meta|facebook|apple|openai|netflix)", re.I), "Team"),
    (re.compile(r"novel|proprietary|technology edge|cryptograph|algorithm|architecture advantage|tech advantage|zk", re.I), "Technology Edge"),
    (re.compile(r"revenue|fees?|apy|yield|margin|pricing|cost structure|take rate|moneti[sz]ation", re.I), "Economics/Pricing"),
    (re.compile(r"TAM|market size|market share|addressable market|position(ing)?", re.I), "Market Position"),
]

NEUTRAL_RULES: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"mechanic|how it work|workflow|process flow", re.I), "Mechanics"),
    (re.compile(r"architecture|module|component|layer|design", re.I), "Architecture"),
    (re.compile(r"roadmap|milestone|timeline|upcoming|planned|launch", re.I), "Roadmap"),
    (re.compile(r"governance (process|proposal|vote)|quorum|delegate|dao", re.I), "Governance Process"),
    (re.compile(r"tokenomic|supply split|distribution|allocation", re.I), "Tokenomics Summary"),
    (re.compile(r"budget|grant|allocation of funds|resource allocation", re.I), "Resource Allocation"),
]


@dataclass
class TagInference:
    label: str
    tag: str
    signals: List[str]


def _apply_rules(text: str, rules: List[Tuple[re.Pattern, str]]) -> Tuple[str | None, List[str]]:
    hits: List[str] = []
    chosen: str | None = None
    for pat, tag in rules:
        if pat.search(text):
            if not chosen:
                chosen = tag
            hits.append(tag)
    return chosen, hits


def infer_tag(text: str) -> TagInference:
    """Infer (label, tag) with precedence Risk > Advantage > Neutral.

    Returns the first matching tag in precedence order and records all matched
    tags in the same tier under `signals` for rationale support.
    """
    tl = text.lower()
    risk_tag, risk_hits = _apply_rules(tl, RISK_RULES)
    if risk_tag:
        return TagInference(TopLevel.Risk.value, risk_tag, risk_hits)
    adv_tag, adv_hits = _apply_rules(tl, ADVANTAGE_RULES)
    if adv_tag:
        return TagInference(TopLevel.Advantage.value, adv_tag, adv_hits)
    neut_tag, neut_hits = _apply_rules(tl, NEUTRAL_RULES)
    if neut_tag:
        return TagInference(TopLevel.Neutral.value, neut_tag, neut_hits)
    # Fallback: Neutral Mechanics (generic)
    return TagInference(TopLevel.Neutral.value, "Mechanics", [])


def infer_with_validation(text: str) -> TagInference:
    inf = infer_tag(text)
    if not validate(inf.label, inf.tag):  # pragma: no cover (should not happen)
        # degrade to generic Neutral
        return TagInference(TopLevel.Neutral.value, "Mechanics", [])
    return inf


__all__ = ["infer_tag", "infer_with_validation", "TagInference"]
