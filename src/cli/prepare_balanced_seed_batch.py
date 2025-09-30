from __future__ import annotations
"""Prepare a balanced seed batch across candidateType and quality buckets.

Algorithm:
 1. Group insights by candidateType.
 2. Guarantee --minPerType (if available) from each group.
 3. Remaining slots filled proportionally to group size, while trying to spread
    quality buckets (high > mid > low) using a simple round-robin.
 4. Shuffle final output for labeling order randomization.

Usage:
  python src/cli/prepare_balanced_seed_batch.py --in data/eigenlayer.insights.jsonl \
      --out data/seed_batch_balanced.v1.jsonl --total 60 --minPerType 5 --seed 42
"""
import argparse, json, random, os, sys
from collections import defaultdict, deque
from typing import Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

QUALITY_ORDER = ['high','mid','low']  # preference order when filling

def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def quality_bucket(q: float) -> str:
    if q is None: return 'low'
    try: q = float(q)
    except Exception: return 'low'
    if q >= 0.75: return 'high'
    if q >= 0.45: return 'mid'
    return 'low'

def load_groups(inp: str):
    groups: Dict[str, List[Dict]] = defaultdict(list)
    for obj in iter_jsonl(inp):
        text = obj.get('text')
        if not text: continue
        ctype = obj.get('candidateType','other') or 'other'
        qbucket = quality_bucket(obj.get('qualityScore'))
        obj['_qbucket'] = qbucket
        groups[ctype].append(obj)
    return groups

def select_balanced(groups: Dict[str,List[Dict]], total: int, min_per_type: int, seed: int):
    random.seed(seed)
    # Shuffle each group
    for g in groups.values():
        random.shuffle(g)
    selected = []
    # Step 1: guarantee min_per_type
    allocated = {}
    for ctype, items in groups.items():
        take = min(min_per_type, len(items))
        selected.extend(items[:take])
        allocated[ctype] = take
    # Remaining slots
    remaining = total - len(selected)
    if remaining <= 0:
        return selected[:total], allocated
    # Build quality-based queues per type
    queues: Dict[str, Dict[str, deque]] = {}
    for ctype, items in groups.items():
        qbuckets = defaultdict(list)
        for it in items[allocated.get(ctype,0):]:
            qbuckets[it['_qbucket']].append(it)
        # shuffle each bucket then convert to deque
        queues[ctype] = {qb: deque(random.sample(lst, len(lst))) for qb, lst in qbuckets.items()}
    # Proportional fill weights (remaining size per type)
    weights = []
    for ctype, items in groups.items():
        rem = max(0, len(items) - allocated[ctype])
        if rem > 0:
            weights.append((ctype, rem))
    total_weight = sum(w for _, w in weights) or 1
    # Turn into repeated sequence by approximate proportion
    seq = []
    for ctype, w in weights:
        count = max(1, int(round(remaining * (w / total_weight))))
        seq.extend([ctype]*count)
    random.shuffle(seq)
    # Round-robin through QUALITY_ORDER for each ctype appearance
    for ctype in seq:
        if remaining <= 0: break
        bucket_map = queues.get(ctype)
        if not bucket_map:
            continue
        picked = None
        for qb in QUALITY_ORDER:
            dq = bucket_map.get(qb)
            if dq and dq:
                picked = dq.popleft()
                break
        if picked:
            selected.append(picked)
            allocated[ctype] += 1
            remaining -= 1
    # If still remaining (due to rounding), fill any leftover
    if remaining > 0:
        leftovers = []
        for ctype, bucket_map in queues.items():
            for dq in bucket_map.values():
                leftovers.extend(list(dq))
        random.shuffle(leftovers)
        selected.extend(leftovers[:remaining])
    return selected[:total], allocated

def main(argv=None):
    ap = argparse.ArgumentParser(description='Prepare balanced seed batch across candidateType and quality heuristics.')
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--total', type=int, default=60)
    ap.add_argument('--minPerType', type=int, default=5)
    ap.add_argument('--seed', type=int, default=42)
    args = ap.parse_args(argv)
    groups = load_groups(args.inp)
    if not groups:
        print('No insights found.', file=sys.stderr); sys.exit(1)
    selected, allocated = select_balanced(groups, args.total, args.minPerType, args.seed)
    random.shuffle(selected)
    with open(args.out,'w',encoding='utf-8') as w:
        for idx, obj in enumerate(selected, start=1):
            rec = {
                'id': idx,
                'text': obj.get('text'),
                'sourceUrl': obj.get('sourceUrl'),
                'candidateType': obj.get('candidateType','other'),
                'qualityScore': obj.get('qualityScore'),
                'provenance': obj.get('provenance','scraped'),
                'sample_phase': 'seed-balanced'
            }
            w.write(json.dumps(rec, ensure_ascii=False) + '\n')
    summary = {
        'written': len(selected),
        'allocated': allocated,
        'unique_types': len(groups)
    }
    sys.stdout.write(json.dumps(summary, indent=2) + '\n')

if __name__ == '__main__':  # pragma: no cover
    main()
