#!/usr/bin/env python
"""Health check for a prediction JSONL file.

Checks:
  - Neutral ratio within bounds (default 0.2-0.55)
  - Each label support >= min_support proportion (default 0.10)
  - (Optional) Mean cluster entropy (requires precomputed cluster report or run quick hash KMeans) < entropy_max
Exit codes:
  0 = pass, 1 = soft warnings only (if --strict not set), 2 = hard fail (strict or severe breach)

Usage:
  python scripts/check_health.py --pred out/insights_classified.jsonl \
    --neutral-min 0.2 --neutral-max 0.55 --min-support 0.1 --entropy-max 1.3 --k 8
"""
import argparse, json, math, random, sys, hashlib
from pathlib import Path
from collections import Counter, defaultdict

try:
    from sklearn.cluster import KMeans
except Exception:
    KMeans = None

LABELS = ["Advantage","Risk","Neutral"]


def load_jsonl(p: Path):
    rows=[]
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip();
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
    return rows


def hash_embed(text: str, dim: int = 128):
    vec=[0.0]*dim
    for tok in text.lower().split():
        hv = int(hashlib.md5(tok.encode()).hexdigest(),16)
        vec[hv % dim]+=1
    norm = math.sqrt(sum(v*v for v in vec)) or 1.0
    return [v/norm for v in vec]


def cluster_entropy(rows, k=8):
    if KMeans is None:
        return None
    texts=[r['text'] for r in rows if 'text' in r]
    X=[hash_embed(t) for t in texts]
    km = KMeans(n_clusters=k, n_init=8, random_state=42)
    labels = km.fit_predict(X)
    clusters=defaultdict(list)
    for i,cid in enumerate(labels):
        clusters[cid].append(i)
    ent=[]
    for cid, idxs in clusters.items():
        lab_dist=Counter(rows[i]['label'] for i in idxs)
        total=sum(lab_dist.values()) or 1
        H=0.0
        for c in lab_dist.values():
            p=c/total
            if p>0: H -= p*math.log2(p)
        ent.append(H)
    return sum(ent)/len(ent) if ent else 0.0


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pred', required=True)
    ap.add_argument('--neutral-min', type=float, default=0.2)
    ap.add_argument('--neutral-max', type=float, default=0.55)
    ap.add_argument('--min-support', type=float, default=0.10)
    ap.add_argument('--entropy-max', type=float, default=1.3)
    ap.add_argument('--k', type=int, default=8)
    ap.add_argument('--strict', action='store_true')
    args=ap.parse_args()

    recs = load_jsonl(Path(args.pred))
    if not recs:
        print(json.dumps({'error':'no_records'})); sys.exit(2)

    label_counts=Counter(r.get('label') for r in recs)
    total=sum(label_counts.values()) or 1
    neutral_ratio = label_counts.get('Neutral',0)/total

    issues=[]; warnings=[]

    if neutral_ratio < args.neutral_min or neutral_ratio > args.neutral_max:
        issues.append({'type':'neutral_ratio', 'value': round(neutral_ratio,3)})

    for lab in LABELS:
        prop = label_counts.get(lab,0)/total
        if prop < args.min_support:
            issues.append({'type':'low_support','label':lab,'value':round(prop,3)})

    mean_entropy=None
    if KMeans is not None and total >= args.k*2:
        mean_entropy = cluster_entropy(recs, k=args.k)
        if mean_entropy is not None and mean_entropy > args.entropy_max:
            warnings.append({'type':'high_entropy','value':round(mean_entropy,3)})

    status = 0
    if issues and args.strict:
        status = 2
    elif issues:
        status = 1

    out = {
        'counts': label_counts,
        'total': total,
        'neutral_ratio': round(neutral_ratio,3),
        'mean_cluster_entropy': round(mean_entropy,3) if mean_entropy is not None else None,
        'issues': issues,
        'warnings': warnings,
        'status': status
    }
    print(json.dumps(out, indent=2))
    sys.exit(status)

if __name__ == '__main__':
    main()
