from __future__ import annotations
import re, json, hashlib, math
from dataclasses import dataclass
from typing import Iterable, List, Dict, Tuple, Sequence, Set, Callable

SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+|[\u2022\-\u2013] +")  # punctuation or bullet separators

NOISE_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"accept cookies", r"subscribe to", r"newsletter", r"back to top", r"all rights reserved",
        r"privacy policy", r"terms of service", r"follow us", r"cookie settings", r"sign up", r"log in"
    ]
]

CRYPTO_KEYWORDS = {
    "restake","restaking","validator","staking","operator","slashing","slash","delegation","delegate",
    "governance","emission","incentive","tokenomics","audit","audited","security","protocol","slashed",
    "risk","uncertainty","penalty","penalties","rewards","reward","stake","tvl","collateral"
}

NUMBER_PATTERN = re.compile(r"(\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b|\b\d+%\b|\b\d{4}\b)")
FLUFF_PATTERN = re.compile(r"world[- ]class|pioneer|innovative|cutting-edge|revolutionary|paradigm", re.I)

PUNCT_STRIP = None  # Placeholder not used; \p classes unsupported in stdlib re

@dataclass
class InsightCandidate:
    source_url: str
    section: str
    text: str  # cleaned candidate sentence or merged sentences
    evidence: List[str]
    candidate_type: str = 'other'  # metric|risk|roadmap|adoption|tokenomics|security|other
    quality: float = 0.0      # 0-1 quality score


def clean_text(raw: str) -> str:
    lines: List[str] = []
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        lowered = s.lower()
        if any(p.search(lowered) for p in NOISE_PATTERNS):
            continue
        # collapse internal whitespace
        s = re.sub(r"\s+", " ", s)
        lines.append(s)
    return "\n".join(lines)


def split_sentences(text: str) -> List[str]:
    # Replace bullets with space to make regex splitting safe
    parts = re.split(SPLIT_REGEX, text)
    out = []
    for p in parts:
        s = p.strip()
        if not s:
            continue
        # Skip if extremely short
        if len(s) < 5:
            continue
        out.append(s)
    return out


def is_candidate(sent: str) -> bool:
    l = sent.lower()
    if FLUFF_PATTERN.search(l):
        return False
    # must contain either number, crypto keyword, or risk/security term
    if NUMBER_PATTERN.search(sent):
        return True
    if any(k in l for k in CRYPTO_KEYWORDS):
        return True
    # allow proper noun patterns (capitalized word not at start?) heuristic omitted for simplicity
    return False


def merge_adjacent(cands: List[str]) -> List[Tuple[str, List[str]]]:
    merged: List[Tuple[str,List[str]]] = []
    i = 0
    while i < len(cands):
        cur = cands[i]
        evid = [cur]
        # Simple heuristic: if next sentence is short (<80 chars) and shares a keyword, merge
        if i + 1 < len(cands):
            nxt = cands[i+1]
            if len(nxt) < 80 and share_keyword(cur, nxt):
                cur = cur.rstrip('.') + '. ' + nxt
                evid.append(nxt)
                i += 1
        merged.append((cur, evid))
        i += 1
    return merged


def share_keyword(a: str, b: str) -> bool:
    al = a.lower(); bl = b.lower()
    for k in CRYPTO_KEYWORDS:
        if k in al and k in bl:
            return True
    return False


def normalize_for_dedupe(text: str) -> str:
    t = text.lower()
    t = re.sub(r"[^a-z0-9 ]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def dedupe(insights: List[InsightCandidate]) -> List[InsightCandidate]:
    seen: Set[str] = set()
    out: List[InsightCandidate] = []
    for ins in insights:
        key = normalize_for_dedupe(ins.text)
        if key in seen:
            continue
        seen.add(key)
        out.append(ins)
    return out


def extract_section(url: str) -> str:
    # crude section: first path component after domain
    m = re.match(r"https?://[^/]+/([^/?#]+)/?", url)
    if m:
        sec = m.group(1)
        if len(sec) > 40:
            return sec[:40]
        return sec
    return "root"


def iter_scraped_jsonl(path: str) -> Iterable[Dict]:
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


TYPE_KEYWORDS = {
    'metric': [r"\b(users?|wallets?|validators?|tvl|apy|apr|throughput|latency|max TPS|transactions?)\b", r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b"],
    'risk': [r"\brisks?\b", r"\b(exploit|hack|outage|slashing|penalt(y|ies)|uncertaint(y|ies))\b"],
    'roadmap': [r"\b(q[1-4]\s*20\d{2})\b", r"\b(launch|ship|release|upgrade|milestone)\b"],
    'adoption': [r"\b(partner(ship)?|integration|adopt(ed|ion)|listing|exchange)\b"],
    'tokenomics': [r"\b(emission|emissions|inflation|supply|burn|vesting|unlock|tokenomics)\b"],
    'security': [r"\b(audit(ed)?|auditor|security|formal verification|bug bounty)\b"],
}

def infer_candidate_type(text: str) -> str:
    lt = text.lower()
    for t, pats in TYPE_KEYWORDS.items():
        for pat in pats:
            if re.search(pat, lt, re.I):
                return t
    return 'other'

def compute_quality(text: str, evidence: Sequence[str]) -> float:
    # Heuristic components: length adequacy, numeric density, keyword richness, evidence span coherence
    length = len(text)
    length_score = 1.0 if 60 <= length <= 220 else (0.6 if 40 <= length < 60 or 220 < length <= 280 else 0.3)
    nums = len(NUMBER_PATTERN.findall(text))
    num_score = min(nums / 3.0, 1.0)  # up to 3 numbers saturates
    kw_hits = sum(1 for k in CRYPTO_KEYWORDS if k in text.lower())
    kw_score = min(kw_hits / 5.0, 1.0)
    # Evidence coherence: if merged evidence sentences share keyword -> boost
    if len(evidence) > 1 and share_keyword(evidence[0], evidence[-1]):
        coher = 1.0
    else:
        coher = 0.5 if len(evidence) > 1 else 0.8
    raw = 0.35*length_score + 0.25*num_score + 0.25*kw_score + 0.15*coher
    return round(min(max(raw, 0.0), 1.0),3)

def extract_insights(scraped_path: str, out_path: str, target_count: Tuple[int,int]=(50,100)) -> Dict[str,int]:
    raw_candidates: List[InsightCandidate] = []
    for rec in iter_scraped_jsonl(scraped_path):
        url = rec.get('url') or rec.get('sourceUrl') or ''
        if not url:
            continue
        section = extract_section(url)
        cleaned = clean_text(rec.get('text',''))
        sentences = split_sentences(cleaned)
        filtered = [s for s in sentences if is_candidate(s)]
        merged = merge_adjacent(filtered)
        for text, evid in merged:
            # enforce max length ~ 300 chars
            if len(text) > 300:
                continue
            ctype = infer_candidate_type(text)
            quality = compute_quality(text, evid)
            raw_candidates.append(InsightCandidate(source_url=url, section=section, text=text, evidence=evid, candidate_type=ctype, quality=quality))
    deduped = dedupe(raw_candidates)
    # simple truncation to target upper bound, later we can balance categories
    low, high = target_count
    final = deduped[:high]

    with open(out_path, 'w', encoding='utf-8') as w:
        for ins in final:
            obj = {
                "sourceUrl": ins.source_url,
                "section": ins.section,
                "text": ins.text,
                "evidence": ins.evidence,
                "candidateType": ins.candidate_type,
                "qualityScore": ins.quality,
                "provenance": "scraped",
            }
            w.write(json.dumps(obj, ensure_ascii=False) + "\n")

    return {"raw_candidates": len(raw_candidates), "deduped": len(deduped), "written": len(final)}

__all__ = [
    "clean_text","split_sentences","is_candidate","merge_adjacent","dedupe","extract_insights","extract_section","InsightCandidate"
]
