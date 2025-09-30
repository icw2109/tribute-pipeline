#!/usr/bin/env python
"""Aggregate diagnostics over a prediction JSONL file.

Outputs JSON with:
  label_dist: counts per label
  confidence_bins: list of {range, count}
  provisional_counts: counts of provisionalLabel by value
  provenance_counts: counts of provenance tokens (from debug.provenance list)
  avg_confidence_per_label
  neutral_ratio
  disagreement_proxy: heuristic using provisional + margin/fallback markers

Usage:
  python scripts/diagnostics_summary.py --pred out/zs_primary_selftrain.jsonl --bins 10

File requirements:
  Each record should have: label, confidence. If debug present with provenance list, it's used for provenance_counts.
"""
import argparse, json, math
from pathlib import Path
from collections import Counter, defaultdict

def load_jsonl(path: Path):
    data = []
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                data.append(json.loads(line))
            except Exception:
                pass
    return data


def bin_conf(conf, bins):
    # bins equally spaced in [0,1]
    idx = min(bins-1, int(conf * bins))
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pred', required=True)
    ap.add_argument('--bins', type=int, default=10)
    args = ap.parse_args()

    recs = load_jsonl(Path(args.pred))
    if not recs:
        print(json.dumps({'error':'no_records','file':args.pred}))
        return
    label_dist = Counter()
    conf_bins = [0]*args.bins
    per_label_conf = defaultdict(list)
    provisional = Counter()
    provenance_counts = Counter()

    for r in recs:
        lab = r.get('label')
        label_dist[lab]+=1
        c = r.get('confidence')
        if isinstance(c,(int,float)):
            conf_bins[bin_conf(float(c), args.bins)] += 1
            per_label_conf[lab].append(float(c))
        if 'provisionalLabel' in r:
            provisional[r['provisionalLabel']] += 1
        dbg = r.get('debug')
        if isinstance(dbg, dict):
            prov = dbg.get('provenance')
            if isinstance(prov, list):
                for p in prov:
                    provenance_counts[p]+=1

    avg_conf_per_label = {k: round(sum(v)/len(v),3) for k,v in per_label_conf.items() if v}
    total = sum(label_dist.values()) or 1
    neutral_ratio = label_dist.get('Neutral',0)/total

    # Format confidence bins with ranges
    bin_ranges = []
    for i,count in enumerate(conf_bins):
        lo=i/args.bins; hi=(i+1)/args.bins
        bin_ranges.append({'range': f"{lo:.2f}-{hi:.2f}", 'count': count})

    out = {
        'count': total,
        'label_dist': label_dist,
        'avg_confidence_per_label': avg_conf_per_label,
        'confidence_bins': bin_ranges,
        'provisional_counts': provisional,
        'provenance_counts': provenance_counts,
        'neutral_ratio': round(neutral_ratio,3),
    }
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
