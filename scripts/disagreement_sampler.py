#!/usr/bin/env python
"""Generate a disagreement-focused sample between two prediction files.

Usage:
  python scripts/disagreement_sampler.py --a out/zs_primary.jsonl --b out/zs_primary_selftrain.jsonl --out out/disagreement_sample.jsonl --limit 40

Selection logic:
  1. Pairs with differing labels.
  2. If fewer than --limit, add cases with provisionalLabel present in either file.
  3. If still fewer, add high-confidence disagreements (difference in confidence >= 0.25).

Assumes both files contain records keyed by exact text field.
"""
import argparse, json
from pathlib import Path


def load(path: Path):
    data = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data.append(json.loads(line))
            except Exception:
                pass
    return data


def index_by_text(recs):
    return {r.get('text'): r for r in recs if r.get('text')}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--a', required=True, help='First predictions file')
    ap.add_argument('--b', required=True, help='Second predictions file')
    ap.add_argument('--out', required=True, help='Output JSONL sample')
    ap.add_argument('--limit', type=int, default=50)
    args = ap.parse_args()

    A = index_by_text(load(Path(args.a)))
    B = index_by_text(load(Path(args.b)))

    texts = set(A.keys()) & set(B.keys())
    disagreements = []
    provisional = []
    high_conf_gap = []

    for t in texts:
        ra = A[t]; rb = B[t]
        la, lb = ra.get('label'), rb.get('label')
        ca, cb = ra.get('confidence'), rb.get('confidence')
        if la != lb:
            disagreements.append({'text': t, 'a_label': la, 'b_label': lb, 'a_conf': ca, 'b_conf': cb})
        else:
            # collect potential high-conf-gap same-label cases for last resort
            if ca is not None and cb is not None and abs(ca - cb) >= 0.25:
                high_conf_gap.append({'text': t, 'a_label': la, 'b_label': lb, 'a_conf': ca, 'b_conf': cb, 'gap': abs(ca-cb)})
        if ra.get('provisionalLabel') or rb.get('provisionalLabel'):
            provisional.append({'text': t, 'a_label': la, 'b_label': lb, 'a_conf': ca, 'b_conf': cb, 'a_provisional': ra.get('provisionalLabel'), 'b_provisional': rb.get('provisionalLabel')})

    # Assemble sample prioritized by: disagreements -> provisional -> high_conf_gap
    sample = []
    for bucket in (disagreements, provisional, high_conf_gap):
        for item in bucket:
            if len(sample) >= args.limit:
                break
            sample.append(item)
        if len(sample) >= args.limit:
            break

    with Path(args.out).open('w', encoding='utf-8') as w:
        for r in sample:
            w.write(json.dumps(r, ensure_ascii=False) + '\n')

    print(json.dumps({
        'counts': {
            'disagreements': len(disagreements),
            'provisional': len(provisional),
            'high_conf_gap': len(high_conf_gap)
        },
        'written': len(sample),
        'out': args.out
    }, indent=2))

if __name__ == '__main__':
    main()
