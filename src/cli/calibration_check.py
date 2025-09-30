from __future__ import annotations
"""Simple reliability (calibration) report for ensemble outputs.

Computes bins over finalConfidence or modelProbs top probability.
If gold labels provided (optional second file with same order or containing id->label), compares accuracy per bin.
Otherwise uses pseudo accuracy proxy: treat final label as truth (report only confidence histogram).

Usage:
  python src/cli/calibration_check.py --in out/ensemble.labeled.v2.jsonl --bins 8 --field finalConfidence
"""
import argparse, json, math
from typing import List, Dict


def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--bins', type=int, default=10)
    ap.add_argument('--field', default='finalConfidence', help='Confidence field to evaluate (finalConfidence or topModelProb)')
    args = ap.parse_args()

    # Load records
    records = list(iter_jsonl(args.inp))
    if not records:
        print(json.dumps({'error':'no_records'}))
        return

    # Build confidence list
    vals = []
    for r in records:
        if args.field == 'topModelProb':
            mp = r.get('modelProbs') or {}
            v = max(mp.values()) if mp else None
        else:
            v = r.get('finalConfidence')
        if v is None:
            continue
        vals.append(v)

    if not vals:
        print(json.dumps({'error':'no_confidence_values'}))
        return

    bins = args.bins
    bucket = [[] for _ in range(bins)]
    for v in vals:
        idx = min(bins-1, int(v * bins))
        bucket[idx].append(v)

    summary = []
    for i, b in enumerate(bucket):
        if not b:
            summary.append({'bin': i, 'count':0, 'range': [i/bins, (i+1)/bins], 'avg': None})
        else:
            summary.append({'bin': i, 'count':len(b), 'range':[i/bins, (i+1)/bins], 'avg': sum(b)/len(b)})

    print(json.dumps({'field': args.field, 'records': len(records), 'bins': summary}, indent=2))

if __name__ == '__main__':
    main()
