from __future__ import annotations
import re, json, collections
from .classify import classify, ClassificationResult
from .metrics import extract_metrics, Metric
import random
from dataclasses import dataclass
from typing import Iterable, List, Dict, Tuple, Set

# Enrich extraction with candidate type + quality (reuse core heuristics if available)
try:  # lightweight, avoid hard dependency breakage
    from core.insight_extract import infer_candidate_type as _infer_candidate_type, compute_quality as _compute_quality
except Exception:  # fallback simple implementations
    def _infer_candidate_type(text: str) -> str:
        lt = text.lower()
        if any(re.search(p, lt) for p in [r"\b(q[1-4]\s*20\d{2})\b", r"\b(launch|upgrade|release)\b"]):
            return 'roadmap'
        if any(k in lt for k in ("slashing","slash","penalty","risk","exploit")):
            return 'risk'
        if any(k in lt for k in ("audit","security","bug bounty")):
            return 'security'
        if any(k in lt for k in ("emission","supply","inflation","tokenomics","vesting","unlock")):
            return 'tokenomics'
        if any(k in lt for k in ("partner","integration","adopt","listing")):
            return 'adoption'
        if any(re.search(r"\b(users?|wallets?|validators?|tps|throughput|latency|mb/s)\b", lt)):
            return 'metric'
        return 'other'
    def _compute_quality(text: str, evidence: List[str]) -> float:
        length = len(text)
        length_score = 1.0 if 60 <= length <= 220 else (0.6 if 40 <= length < 60 or 220 < length <= 300 else 0.3)
        nums = len(re.findall(r"\b\d+\b", text))
        num_score = min(nums/3.0, 1.0)
        kw_hits = sum(1 for k in ("risk","slash","validator","staking","operator","throughput","mb/s") if k in text.lower())
        kw_score = min(kw_hits/5.0, 1.0)
        coher = 1.0 if len(evidence) > 1 else 0.7
        raw = 0.35*length_score + 0.25*num_score + 0.25*kw_score + 0.15*coher
        return round(min(max(raw,0.0),1.0),3)

SPLIT_REGEX = re.compile(r"(?<=[.!?])\s+|[\u2022\-\u2013] +")

# Investor signal patterns (expansion for investor-centric cues)
# Key: canonical signal name, Value: compiled regex
INVESTOR_SIGNAL_PATTERNS: dict[str, re.Pattern] = {
    "traction": re.compile(r"\b(users?|wallets?|validators?|tvl|volume|delegat|adoption|growth|retention|cohort)\b", re.I),
    "pricing_economics": re.compile(r"\b(revenue|fees?|apy|yield|margin|pricing|cost|take rate|moneti[sz]ation|economic model)\b", re.I),
    "market": re.compile(r"\b(TAM|total addressable market|market size|sector|vertical|market share)\b", re.I),
    "team": re.compile(r"\b(team|founder|co-founder|lead engineer|researcher|hiring|hired|hire|ex-(google|amazon|meta|facebook|apple|openai|netflix))\b", re.I),
    "technology": re.compile(r"\b(throughput|latency|tps|scalab|performance|zk|zero-knowledge|encryption|algorithm|proof|consensus|architecture|module)\b", re.I),
    "security": re.compile(r"\b(audit|audited|bug bounty|vulnerab|exploit|attack|slash|slashing|security)\b", re.I),
    "compliance": re.compile(r"\b(regulat|compliance|legal|jurisdiction|licen[cs]e)\b", re.I),
    "tokenomics": re.compile(r"\b(emission|supply|inflation|vesting|unlock|distribution|allocation|burn|tokenomic)\b", re.I),
    "governance": re.compile(r"\b(governance|proposal|vote|quorum|delegate|dao)\b", re.I),
    "partnerships": re.compile(r"\b(partner|integration|alliance|ecosystem|collaborat)\b", re.I),
    "competition": re.compile(r"\b(competitor|competition|alternative|fragment|substitute)\b", re.I),
    "risk": re.compile(r"\b(risk|uncertain|downtime|penalty|penalties|loss)\b", re.I),
    "roadmap": re.compile(r"\b(roadmap|milestone|timeline|upcoming|planned|launch|release)\b", re.I),
}

NOISE_PATTERNS = [
    re.compile(p, re.I) for p in [
        r"accept cookies", r"subscribe to", r"newsletter", r"back to top", r"all rights reserved",
        r"privacy policy", r"terms of service", r"follow us", r"cookie settings", r"sign up", r"log in",
        r"javascript is not essential", r"please turn javascript on", r"enable javascript"
    ]
]

CRYPTO_KEYWORDS = {
    "restake","restaking","validator","staking","operator","slashing","slash","delegation","delegate",
    "governance","emission","incentive","tokenomics","audit","audited","security","protocol","slashed",
    "risk","uncertainty","penalty","penalties","rewards","reward","stake","tvl","collateral",
    # Domain / EigenLayer style additions
    "eigenlayer","eigen","avs","restaked","delegator","delegators","operator set","actively validated service"
}

NUMBER_PATTERN = re.compile(r"(\b\d{1,3}(?:,\d{3})*(?:\.\d+)?%?\b|\b\d+%\b|\b\d{4}\b)")
FLUFF_PATTERN = re.compile(r"world[- ]class|pioneer|innovative|cutting-edge|revolutionary|paradigm", re.I)

# Default baseline neutral inclusion length (can be overridden per call)
BASELINE_NEUTRAL_MIN_LEN = 40

@dataclass
class InsightCandidate:
    source_url: str
    section: str
    text: str
    evidence: List[str]


def clean_text(raw: str) -> str:
    lines: List[str] = []
    replacements = {
        "â€™": "'","â€˜": "'","â€œ": '"',"â€": '"',"â€“": "-","â€”": "-","â€¢": "-","Â©": "©"
    }
    for ln in raw.splitlines():
        s = ln.strip()
        if not s:
            continue
        lowered = s.lower()
        if any(p.search(lowered) for p in NOISE_PATTERNS):
            continue
        for k,v in replacements.items():
            if k in s:
                s = s.replace(k, v)
        s = re.sub(r"\s+", " ", s)
        lines.append(s)
    return "\n".join(lines)


def split_sentences(text: str) -> List[str]:
    parts = re.split(SPLIT_REGEX, text)
    out = []
    for p in parts:
        s = p.strip()
        if not s:
            continue
        if len(s) < 5:
            continue
        out.append(s)
    return out


def is_candidate(sent: str) -> bool:
    l = sent.lower()
    if FLUFF_PATTERN.search(l):
        return False
    if NUMBER_PATTERN.search(sent):
        return True
    if any(k in l for k in CRYPTO_KEYWORDS):
        return True
    if len(sent) >= BASELINE_NEUTRAL_MIN_LEN:
        return True
    return False


def share_keyword(a: str, b: str) -> bool:
    al = a.lower(); bl = b.lower()
    for k in CRYPTO_KEYWORDS:
        if k in al and k in bl:
            return True
    return False


def merge_adjacent(cands: List[str]) -> List[Tuple[str, List[str]]]:
    merged: List[Tuple[str,List[str]]] = []
    i = 0
    while i < len(cands):
        cur = cands[i]
        evid = [cur]
        if i + 1 < len(cands):
            nxt = cands[i+1]
            if len(nxt) < 80 and share_keyword(cur, nxt):
                cur = cur.rstrip('.') + '. ' + nxt
                evid.append(nxt)
                i += 1
        merged.append((cur, evid))
        i += 1
    return merged


def _detect_investor_signals(text: str) -> List[str]:
    hits = []
    for name, pat in INVESTOR_SIGNAL_PATTERNS.items():
        if pat.search(text):
            hits.append(name)
    return sorted(hits)


def _atomic_split(text: str, max_len: int = 180) -> List[str]:
    """Split long merged sentences into atomic clauses <= max_len.

    Strategy:
      * If already <= max_len return as-is.
      * Tokenize by high-value clause delimiters (semicolon, em/en dash, colon, ' and ', ' but ', ' however ').
      * Sequentially accumulate segments ensuring each chunk <= max_len.
      * Fallback: hard split at nearest space before max_len if a single residual chunk remains too long.
    """
    t = text.strip()
    if len(t) <= max_len:
        return [t]
    # Normalize dashes
    norm = t.replace('—', ' - ').replace('–', ' - ')
    # Primary clause split
    raw_parts = re.split(r";| - |:|\bhowever\b|\bbut\b|\band\b", norm, flags=re.IGNORECASE)
    parts = [p.strip(" ,.") for p in raw_parts if p and len(p.strip()) > 3]
    out: List[str] = []
    cur = ''
    for p in parts:
        candidate = (p if not cur else cur + ', ' + p)
        if len(candidate) <= max_len:
            cur = candidate
        else:
            if cur:
                out.append(cur.rstrip(' ,'))
            if len(p) <= max_len:
                cur = p
            else:
                # hard wrap p
                start = 0
                while start < len(p):
                    end = min(start + max_len, len(p))
                    # try backtrack to last space
                    slice_seg = p[start:end]
                    if end < len(p) and ' ' in slice_seg:
                        last_space = slice_seg.rfind(' ')
                        if last_space > 40:  # avoid tiny tail
                            end = start + last_space
                            slice_seg = p[start:end]
                    out.append(slice_seg.strip())
                    start = end
                cur = ''
    if cur:
        out.append(cur.rstrip(' ,'))
    # Final cleanup + ensure period termination for readability (optional)
    cleaned = []
    for seg in out:
        seg = seg.strip()
        if not seg.endswith(('.', '!', '?')):
            seg = seg + '.'
        cleaned.append(seg)
    return cleaned or [t[:max_len]]


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
    m = re.match(r"https?://[^/]+/([^/?#]+)/?", url)
    if m:
        sec = m.group(1)
        if len(sec) > 40:
            return sec[:40]
        return sec
    return "root"


def iter_scraped_jsonl(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


DATE_TOKEN = re.compile(r"\b(19|20|21)\d{2}\b")

def _jaccard(a: str, b: str) -> float:
    STOP = {"the","and","for","to","of","a","an","in"}
    def norm_tokens(s: str):
        raw = re.findall(r"[a-z0-9]+", s.lower())
        out = []
        for tok in raw:
            if tok in STOP:
                continue
            # naive plural strip
            if tok.endswith('s') and len(tok) > 3:
                tok = tok[:-1]
            out.append(tok)
        return set(out)
    sa = norm_tokens(a)
    sb = norm_tokens(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)

def fuzzy_dedupe(insights: List[InsightCandidate], threshold: float=0.9) -> List[InsightCandidate]:
    kept: List[InsightCandidate] = []
    for ins in insights:
        txt = ins.text
        if any(_jaccard(txt, k.text) >= threshold for k in kept):
            continue
        kept.append(ins)
    return kept

# MinHash implementation (simple) for scalability
def _shingles(text: str, k: int = 5) -> set[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {" ".join(tokens[i:i+k]) for i in range(len(tokens)-k+1)} if len(tokens) >= k else set(tokens)

def _minhash_signature(shingles: set[str], hash_funcs: list[tuple[int,int]], mod: int) -> list[int]:
    sig = []
    for (a,b) in hash_funcs:
        m = min(((a*hash(s) + b) % mod) for s in shingles) if shingles else mod
        sig.append(m)
    return sig

def minhash_dedupe(insights: List[InsightCandidate], signature_size: int = 32, bands: int = 8, shingle_k: int = 5, jaccard_check: float = 0.85) -> List[InsightCandidate]:
    if not insights:
        return []
    # prepare hash functions
    random.seed(42)
    mod = 2**32 - 5
    hash_funcs = [(random.randint(1, mod-1), random.randint(0, mod-1)) for _ in range(signature_size)]
    buckets: dict[tuple[int,int], list[int]] = {}
    kept_idx: list[int] = []
    signatures: list[list[int]] = []
    shingles_list: list[set[str]] = []
    rows_per_band = signature_size // bands
    for idx, ins in enumerate(insights):
        sh = _shingles(ins.text, shingle_k)
        shingles_list.append(sh)
        sig = _minhash_signature(sh, hash_funcs, mod)
        signatures.append(sig)
    removed = set()
    for idx, sig in enumerate(signatures):
        if idx in removed:
            continue
        is_dup = False
        for b in range(bands):
            start = b*rows_per_band
            band_key = tuple(sig[start:start+rows_per_band])
            key = (b, hash(band_key))
            lst = buckets.setdefault(key, [])
            for cand in lst:
                if cand in removed:
                    continue
                # confirm with actual Jaccard
                if _jaccard(insights[idx].text, insights[cand].text) >= jaccard_check:
                    is_dup = True
                    removed.add(idx)
                    break
            if is_dup:
                break
            lst.append(idx)
        if not is_dup:
            kept_idx.append(idx)
    return [insights[i] for i in kept_idx]

def extract_insights(
    scraped_path: str,
    out_path: str,
    target_count: tuple[int,int]=(50,100),
    do_classify: bool=False,
    do_metrics: bool=False,
    do_fuzzy: bool=False,
    do_minhash: bool=False,
    compute_confidence: bool=True,
    min_len: int | None = None,
    baseline_neutral_len: int | None = None,
    section_heuristic: str = 'path',
) -> dict[str,int]:
    raw_candidates: List[InsightCandidate] = []
    token_freq: collections.Counter[str] = collections.Counter()
    date_hits = 0
    global BASELINE_NEUTRAL_MIN_LEN
    if baseline_neutral_len is not None and baseline_neutral_len > 0:
        BASELINE_NEUTRAL_MIN_LEN = baseline_neutral_len

    for rec in iter_scraped_jsonl(scraped_path):
        url = rec.get('url') or rec.get('sourceUrl') or ''
        if not url:
            continue
        if section_heuristic == 'none':
            section = 'general'
        else:
            section = extract_section(url)
        cleaned = clean_text(rec.get('text',''))
        sentences = split_sentences(cleaned)
        filtered = [s for s in sentences if is_candidate(s)]
        merged = merge_adjacent(filtered)
        for text, evid in merged:
            # Enforce atomic splitting before candidate registration
            atoms = _atomic_split(text, max_len=180)
            for atom in atoms:
                if len(atom) > 300:  # guardrail (should not happen post split)
                    continue
                raw_candidates.append(InsightCandidate(source_url=url, section=section, text=atom, evidence=evid))
            # lightweight token frequency (lowercase alphanum words)
                for tok in re.findall(r"[a-zA-Z0-9]{3,}", atom.lower()):
                    token_freq[tok] += 1
                date_hits += len(DATE_TOKEN.findall(atom))
    deduped = dedupe(raw_candidates)
    fuzzy_removed = 0
    if do_fuzzy:
        before = len(deduped)
        deduped = fuzzy_dedupe(deduped)
        fuzzy_removed = before - len(deduped)
    minhash_removed = 0
    if do_minhash:
        before2 = len(deduped)
        deduped = minhash_dedupe(deduped)
        minhash_removed = before2 - len(deduped)
    low, high = target_count
    final = deduped[:high]
    metric_token_total = 0
    with open(out_path, 'w', encoding='utf-8') as w:
        for ins in final:
            if min_len is not None and len(ins.text) < min_len:
                continue
            investor_signals = _detect_investor_signals(ins.text)
            rec = {
                "sourceUrl": ins.source_url,
                "section": ins.section,
                "text": ins.text,
                "evidence": ins.evidence,
                # newly added enrichment
                "candidateType": _infer_candidate_type(ins.text),
                "qualityScore": _compute_quality(ins.text, ins.evidence),
                "provenance": "scraped",
                "investorSignals": investor_signals,
            }
            if do_classify:
                cls: ClassificationResult = classify(ins.text)
                rec["category"] = cls.label
                if cls.signals:
                    rec["signals"] = cls.signals
            if do_metrics:
                ms = extract_metrics(ins.text)
                if ms:
                    rec["metrics"] = [m.__dict__ for m in ms]
                    metric_token_total += len(ms)
            # confidence scoring (independent of flags, but uses classification/metrics if present)
            # base weights
            cat_w = {"Risk": 0.9, "Advantage": 0.7, "Neutral": 0.4}
            category = rec.get("category", "Neutral")
            metrics_count = len(rec.get("metrics", []))
            # rarity: average inverse frequency of tokens present (only alphanum >=5)
            toks = [t for t in re.findall(r"[a-z0-9]{5,}", ins.text.lower())]
            rarity_scores = []
            for t in toks:
                freq = token_freq.get(t, 1)
                rarity_scores.append(1.0 / (1 + freq))
            rarity = sum(rarity_scores) / len(rarity_scores) if rarity_scores else 0.0
            if compute_confidence:
                confidence = cat_w.get(category, 0.4)
                confidence += min(metrics_count * 0.05, 0.25)
                confidence += min(rarity, 0.25)
                if confidence > 1.0:
                    confidence = 1.0
                rec["confidence"] = round(confidence, 3)
            w.write(json.dumps(rec, ensure_ascii=False) + "\n")
    top_tokens = token_freq.most_common(12)
    return {
        "raw_candidates": len(raw_candidates),
        "deduped": len(deduped),
        "written": len(final),
        "date_tokens": date_hits,
        "top_tokens": top_tokens,
        "fuzzy_removed": fuzzy_removed,
        "metric_items": metric_token_total,
        "minhash_removed": minhash_removed,
    }

__all__ = [
    'clean_text','split_sentences','is_candidate','merge_adjacent','dedupe','extract_insights','extract_section','InsightCandidate'
]