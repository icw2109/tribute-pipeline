from __future__ import annotations
"""Self-training (pseudo-label) classifier trainer.

Steps:
 1. Read insights JSONL (expects 'text'; will generate heuristics if no provisional label)
 2. Run heuristic classifier to obtain (label, ruleStrength)
 3. Filter by --minRuleStrength (default 0.4)
 4. Vectorize text (TF-IDF) or DistilBERT embeddings if --embeddings backend selected (TODO)
 5. Train LogisticRegression classifier
 6. Optionally perform simple temperature calibration on a holdout split
 7. Save artifacts to output directory: model.pkl, vectorizer.pkl, metadata.json, calibration.json (if applied)

Usage (example):
  python -m cli.self_train --in data/eigenlayer.insights.enriched.jsonl --out models/selftrain --minRuleStrength 0.5
"""
import argparse, json, os, math, random, sys
from pathlib import Path

# Protect against naming collision if someone invokes via python -m cli.self_train from a CWD that shadows package
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from dataclasses import asdict
from typing import List, Dict, Tuple
from pathlib import Path  # (re-import safe)

from insights.vectorizer_registry import get_vectorizer, SbertBackend
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import calibration_curve
import joblib

from insights.heuristic import heuristic_classify
from insights.adin_taxonomy import TAXONOMY_VERSION

LABELS = ["Risk","Advantage","Neutral"]


def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except Exception:
                continue


def split_holdout(X: List[str], y: List[str], frac: float=0.15, seed: int=42) -> Tuple[List[str],List[str],List[str],List[str]]:
    random.seed(seed)
    idx = list(range(len(X)))
    random.shuffle(idx)
    cut = int(len(X)*(1-frac))
    train_idx = idx[:cut]; hold_idx = idx[cut:]
    def take(idxs):
        return [X[i] for i in idxs], [y[i] for i in idxs]
    return *take(train_idx), *take(hold_idx)


def temperature_scale(logits, temp: float):
    import numpy as np
    return logits / temp


def find_temperature(clf: LogisticRegression, X_hold, y_hold, temps=(0.5,0.75,1.0,1.25,1.5)):
    import numpy as np
    probs = clf.predict_proba(X_hold)
    best_t = 1.0
    best_ece = 1e9
    # simple ECE approximation
    y_idx = [LABELS.index(v) for v in y_hold]
    for t in temps:
        scaled = temperature_scale(probs, t)
        scaled = scaled / scaled.sum(axis=1, keepdims=True)
        # 10-bin ECE
        bins = 10
        ece = 0.0
        for b in range(bins):
            lo = b/bins; hi=(b+1)/bins
            sel = (scaled.max(axis=1) >= lo) & (scaled.max(axis=1) < hi)
            if not sel.any():
                continue
            acc = (scaled[sel].argmax(axis=1) == [y_idx[i] for i,v in enumerate(sel) if v]).mean()
            conf = scaled[sel].max(axis=1).mean()
            ece += abs(acc-conf)* (sel.sum()/len(scaled))
        if ece < best_ece:
            best_ece = ece
            best_t = t
    return best_t, best_ece


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True, help='Input insights JSONL')
    ap.add_argument('--out', dest='out_dir', required=True, help='Output directory for artifacts')
    ap.add_argument('--minRuleStrength', type=float, default=0.4, help='Minimum heuristic rule strength to keep as pseudo-label')
    ap.add_argument('--neutralAugment', type=int, default=15, help='Force-include up to N Neutral heuristic samples below threshold (diversity)')
    ap.add_argument('--advAugment', type=int, default=15, help='Force-include up to N Advantage heuristic samples below threshold if scarce')
    ap.add_argument('--requireAllLabels', action='store_true', help='Fail if any top-level label missing after sampling')
    ap.add_argument('--calibrate', action='store_true', help='Apply simple temperature scaling on holdout')
    ap.add_argument('--backend', choices=['tfidf','sbert'], default='tfidf', help='Vectorizer backend: tfidf (default) or sbert')
    ap.add_argument('--sbertModel', default='sentence-transformers/all-MiniLM-L6-v2', help='SentenceTransformer model name when --backend sbert')
    args = ap.parse_args()

    texts: List[str] = []
    labels: List[str] = []
    pool_neutral: List[tuple[str,str,float]] = []
    pool_adv: List[tuple[str,str,float]] = []
    kept = 0; scanned = 0
    for rec in iter_jsonl(args.inp):
        scanned += 1
        txt = rec.get('text')
        if not txt or len(txt) < 15:
            continue
        heur = heuristic_classify(txt)
        lab = heur['label']
        strength = heur['ruleStrength']
        if strength >= args.minRuleStrength:
            texts.append(txt)
            labels.append(lab)
            kept += 1
        else:
            if lab == 'Neutral':
                pool_neutral.append((txt, lab, strength))
            elif lab == 'Advantage':
                pool_adv.append((txt, lab, strength))

    # Augmentation: take highest strength below threshold up to limits
    pool_neutral.sort(key=lambda x: x[2], reverse=True)
    pool_adv.sort(key=lambda x: x[2], reverse=True)
    for src_pool, limit in ((pool_neutral, args.neutralAugment),(pool_adv, args.advAugment)):
        added = 0
        for txt, lab, s in src_pool:
            if added >= limit:
                break
            texts.append(txt)
            labels.append(lab)
            added += 1
            kept += 1

    # Diagnostics
    from collections import Counter
    dist = Counter(labels)
    print(json.dumps({"diagnostics": {"label_counts": dist, "scanned": scanned, "kept": kept}}, default=str))
    if args.requireAllLabels and any(l not in dist for l in LABELS):
        raise SystemExit(f"Missing label(s) after sampling: {set(LABELS) - set(dist)}. Use lower --minRuleStrength or increase augment.")
    if kept < 10:
        raise SystemExit(f"Not enough pseudo-labeled samples retained (kept={kept}). Lower --minRuleStrength or supply more data.")

    X_train, y_train, X_hold, y_hold = split_holdout(texts, labels, frac=0.15)

    vec = get_vectorizer(args.backend, model_name=args.sbertModel)
    Xtr = vec.fit_transform(X_train)
    clf = LogisticRegression(max_iter=400, multi_class='multinomial', class_weight='balanced')
    clf.fit(Xtr, y_train)

    meta = {
        "taxonomyVersion": TAXONOMY_VERSION,
        "labelSet": LABELS,
        "pseudoSamples": kept,
        "minRuleStrength": args.minRuleStrength,
        "calibrated": False,
    }

    calib = None
    if args.calibrate and X_hold:
        Xh = vec.transform(X_hold)
        import numpy as np
        try:
            best_t, ece = find_temperature(clf, Xh, y_hold)
            meta['calibrated'] = True
            meta['temperature'] = best_t
            meta['ece'] = ece
            calib = {"temperature": best_t, "ece": ece}
        except Exception:
            pass

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf, out_dir / 'model.pkl')
    joblib.dump(vec, out_dir / 'vectorizer.pkl')
    with open(out_dir / 'metadata.json','w',encoding='utf-8') as w:
        json.dump(meta, w, indent=2)
    if calib:
        with open(out_dir / 'calibration.json','w',encoding='utf-8') as w:
            json.dump(calib, w, indent=2)
    print(json.dumps({"scanned": scanned, "kept": kept, "out": str(out_dir)}))

if __name__ == '__main__':
    main()
