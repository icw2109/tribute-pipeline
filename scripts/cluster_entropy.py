#!/usr/bin/env python
"""Cluster entropy analysis on prediction file.

Steps:
 1. Load predictions (text,label,confidence, optional debug.provenance).
 2. Embed each text using sentence-transformers if available; fallback to hashed TF-IDF style embedding with simple hashing if not.
 3. Run KMeans clustering (k configurable; default 12).
 4. For each cluster compute:
      - size
      - label distribution
      - label entropy H = -Σ p log2 p
      - dominant label and its proportion
      - avg confidence
 5. Output JSON with per-cluster stats and global summary (mean entropy, weighted mean entropy).

Usage:
  python scripts/cluster_entropy.py --pred out/zs_primary_selftrain.jsonl --k 12

Interpretation:
  - High entropy clusters (close to log2(3) ≈ 1.585) indicate semantic regions where model is unsure / mixed.
  - Clusters with low dominant proportion but high average confidence may indicate overconfidence.
"""
import argparse, json, math, random
from pathlib import Path
from collections import Counter, defaultdict

try:
    from sentence_transformers import SentenceTransformer
    _EMB_BACKEND = 'sbert'
except Exception:  # fallback later
    SentenceTransformer = None
    _EMB_BACKEND = 'hash'

try:
    from sklearn.cluster import KMeans
except Exception:
    KMeans = None

import hashlib


def load_jsonl(path: Path):
    out=[]
    with path.open('r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try: out.append(json.loads(line))
            except: pass
    return out


def hash_embed(text: str, dim: int = 256):
    vec = [0.0]*dim
    tokens = text.lower().split()
    for tok in tokens:
        hv = int(hashlib.md5(tok.encode()).hexdigest(),16)
        idx = hv % dim
        vec[idx] += 1.0
    # L2 normalize
    norm = math.sqrt(sum(v*v for v in vec)) or 1.0
    return [v/norm for v in vec]


def embed_texts(texts, model_name: str = 'all-MiniLM-L6-v2'):
    if _EMB_BACKEND == 'sbert' and SentenceTransformer is not None:
        model = SentenceTransformer(model_name)
        embs = model.encode(texts, batch_size=32, show_progress_bar=False)
        return [list(map(float,e)) for e in embs]
    # fallback
    return [hash_embed(t) for t in texts]


def entropy(dist: Counter):
    total = sum(dist.values()) or 1
    H=0.0
    for c in dist.values():
        p=c/total
        if p>0:
            H -= p*math.log2(p)
    return H


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pred', required=True)
    ap.add_argument('--k', type=int, default=12)
    ap.add_argument('--model', default='all-MiniLM-L6-v2')
    ap.add_argument('--sample', type=int, default=0, help='Optional random subsample size before clustering')
    args=ap.parse_args()

    recs = load_jsonl(Path(args.pred))
    if not recs:
        print(json.dumps({'error':'no_records'}))
        return
    if args.sample and len(recs) > args.sample:
        random.seed(42)
        recs = random.sample(recs, args.sample)

    texts=[r['text'] for r in recs if 'text' in r]
    labels=[r.get('label') for r in recs]
    confidences=[r.get('confidence') for r in recs]

    if KMeans is None:
        print(json.dumps({'error':'sklearn_not_installed'}))
        return

    X = embed_texts(texts, args.model)
    km = KMeans(n_clusters=args.k, n_init=10, random_state=42)
    clust = km.fit_predict(X)

    clusters=defaultdict(list)
    for i,cid in enumerate(clust):
        clusters[cid].append(i)

    cluster_stats=[]
    entropies=[]
    weighted_entropy=0.0
    total=len(recs)
    for cid, idxs in clusters.items():
        ld = Counter(labels[i] for i in idxs)
        H = entropy(ld)
        entropies.append(H)
        weighted_entropy += H * (len(idxs)/total)
        dom_label, dom_count = ld.most_common(1)[0]
        avg_conf = sum(confidences[i] for i in idxs if isinstance(confidences[i],(int,float))) / max(1,sum(1 for i in idxs if isinstance(confidences[i],(int,float))))
        # Ensure serializable label_dist (convert keys & counts to native types)
        label_dist_serializable = {str(k): int(v) for k,v in ld.items()}
        cluster_stats.append({
            'cluster': int(cid),
            'size': int(len(idxs)),
            'label_dist': label_dist_serializable,
            'entropy': round(H,3),
            'dominant_label': dom_label,
            'dominant_prop': round(dom_count/len(idxs),3),
            'avg_confidence': round(avg_conf,3)
        })

    out={
        'k': args.k,
        'backend': _EMB_BACKEND,
        'mean_entropy': round(sum(entropies)/len(entropies),3),
        'weighted_entropy': round(weighted_entropy,3),
        'max_entropy_theoretical': round(math.log2(len(set(l for l in labels if l))),3),
        'clusters': cluster_stats
    }
    print(json.dumps(out, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    main()
