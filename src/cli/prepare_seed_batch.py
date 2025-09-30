from __future__ import annotations
import argparse, json, random, math, os, sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

# For now we only have un-labeled candidateType + qualityScore; we attempt a stratified sample across candidateType buckets

def iter_jsonl(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def quality_bucket(q: float) -> str:
    if q >= 0.75: return 'high'
    if q >= 0.5: return 'mid'
    return 'low'

def plan_counts(total: int, groups: list[str]):
    base = total // len(groups)
    remain = total - base * len(groups)
    plan = {g: base for g in groups}
    # distribute remainder
    for g in groups[:remain]:
        plan[g] += 1
    return plan


def sample_seed(inp: str, out: str, total: int, seed: int):
    random.seed(seed)
    records = list(iter_jsonl(inp))
    # group by candidateType + quality bucket, fallback 'other'
    groups = defaultdict(list)
    for r in records:
        ctype = r.get('candidateType','other') or 'other'
        qb = quality_bucket(float(r.get('qualityScore',0.0)))
        key = f"{ctype}:{qb}"
        groups[key].append(r)
    group_keys = sorted(groups.keys())
    if not group_keys:
        raise SystemExit('No records found in input file.')
    plan = plan_counts(total, group_keys)
    chosen = []
    for g, need in plan.items():
        bucket = groups[g]
        random.shuffle(bucket)
        if len(bucket) <= need:
            chosen.extend(bucket)
        else:
            chosen.extend(bucket[:need])
    # shuffle final order for labeling randomness
    random.shuffle(chosen)
    with open(out,'w',encoding='utf-8') as w:
        for idx, r in enumerate(chosen):
            obj = {
                'id': idx + 1,
                'text': r.get('text'),
                'sourceUrl': r.get('sourceUrl'),
                'candidateType': r.get('candidateType','other'),
                'qualityScore': r.get('qualityScore'),
                'provenance': 'scraped',
                'sample_phase': 'seed'
            }
            w.write(json.dumps(obj, ensure_ascii=False) + '\n')
    return {'written': len(chosen), 'groups': plan}


def main(argv=None):
    ap = argparse.ArgumentParser(description='Prepare seed labeling batch from raw extracted insights.')
    ap.add_argument('--in', dest='inp', required=True, help='Input extracted insights JSONL')
    ap.add_argument('--out', required=True, help='Output seed batch JSONL')
    ap.add_argument('--total', type=int, default=60, help='Total seed items to sample')
    ap.add_argument('--seed', type=int, default=42, help='RNG seed')
    args = ap.parse_args(argv)
    stats = sample_seed(args.inp, args.out, args.total, args.seed)
    sys.stdout.write(json.dumps(stats) + '\n')

if __name__ == '__main__':  # pragma: no cover
    main()
