#!/usr/bin/env python
"""Calibration evaluation script.

Computes reliability curve (bin accuracy vs mean confidence),
Expected Calibration Error (ECE) and Maximum Calibration Error (MCE).

Usage:
  python scripts/calibration_eval.py --pred out/zs_primary_selftrain.jsonl --truth data/labeled.jsonl --bins 8

If --truth omitted, treats 'label' in prediction file as truth and
skips calibration (useful only when you have pseudo-labels).
"""
import argparse, json, math
from pathlib import Path
from typing import List, Dict


def load_jsonl(path: Path) -> List[Dict]:
    items = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                items.append(json.loads(line))
            except Exception:
                pass
    return items


def reliability_bins(preds: List[Dict], truth_map: Dict[str,str] | None, bins: int):
    # If truth_map provided, compare predicted label to truth via text key.
    # Otherwise assume record has 'true' field (not used here) or skip.
    edges = [i / bins for i in range(bins + 1)]
    bucket = [[] for _ in range(bins)]
    for p in preds:
        conf = p.get('confidence')
        if conf is None:
            continue
        # find bin index
        bi = min(bins - 1, int(conf * bins))
        bucket[bi].append(p)
    results = []
    ece = 0.0
    mce = 0.0
    total = sum(len(b) for b in bucket) or 1
    for i, b in enumerate(bucket):
        if not b:
            results.append({'bin': i, 'count': 0, 'conf_mean': None, 'acc': None})
            continue
        conf_mean = sum(r['confidence'] for r in b) / len(b)
        if truth_map:
            correct = 0
            for r in b:
                txt = r.get('text')
                true_label = truth_map.get(txt)
                if true_label is not None and true_label == r.get('label'):
                    correct += 1
            acc = correct / len(b)
            gap = abs(acc - conf_mean)
            weight = len(b) / total
            ece += weight * gap
            mce = max(mce, gap)
        else:
            acc = None
        results.append({'bin': i, 'count': len(b), 'conf_mean': round(conf_mean,3), 'acc': (round(acc,3) if acc is not None else None)})
    return results, (round(ece,4) if truth_map else None), (round(mce,4) if truth_map else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pred', required=True, help='Predictions JSONL with fields text,label,confidence')
    ap.add_argument('--truth', help='Ground truth JSONL with fields text,label (optional)')
    ap.add_argument('--bins', type=int, default=10)
    args = ap.parse_args()

    preds = load_jsonl(Path(args.pred))
    truth_map = None
    if args.truth:
        truth_map = {}
        for r in load_jsonl(Path(args.truth)):
            t = r.get('text'); l = r.get('label')
            if t and l:
                truth_map[t] = l
    bins_out, ece, mce = reliability_bins(preds, truth_map, args.bins)
    print(json.dumps({
        'bins': bins_out,
        'ece': ece,
        'mce': mce,
        'count': len(preds)
    }, indent=2))

if __name__ == '__main__':
    main()
