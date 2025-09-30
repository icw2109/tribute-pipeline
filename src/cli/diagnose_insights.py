from __future__ import annotations
"""Diagnose distribution of extracted insights for sampling & balancing.

If candidateType / qualityScore fields are missing (older extraction), the script
will infer them on-the-fly using the current heuristics from core.insight_extract.

Outputs a JSON summary to stdout plus optional TSV detail bucket file.

Usage:
  python src/cli/diagnose_insights.py --in data/eigenlayer.insights.jsonl
  python src/cli/diagnose_insights.py --in data/eigenlayer.insights.jsonl --detailOut out/diagnose.tsv
"""
import argparse, json, os, sys, statistics, math
from collections import Counter, defaultdict
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from core.insight_extract import infer_candidate_type, compute_quality, NUMBER_PATTERN, CRYPTO_KEYWORDS


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
    if q >= 0.8: return 'vhigh'
    if q >= 0.6: return 'high'
    if q >= 0.4: return 'mid'
    if q >= 0.2: return 'low'
    return 'vlow'


def summarize(path: str):
    ct_counter = Counter()
    qb_counter = Counter()
    length_chars = []
    length_tokens = []
    riskish = 0
    numeric = 0
    total = 0
    examples_per_type = defaultdict(list)
    for obj in iter_jsonl(path):
        text = obj.get('text')
        if not text: continue
        total += 1
        ctype = obj.get('candidateType')
        if not ctype:
            ctype = infer_candidate_type(text)
        # quality
        q = obj.get('qualityScore')
        if q is None:
            # approximate evidence list if present else single sentence
            evidence = obj.get('evidence') or [text]
            try:
                q = compute_quality(text, evidence)
            except Exception:
                q = 0.0
        try:
            q = float(q)
        except Exception:
            q = 0.0
        qb = quality_bucket(q)
        ct_counter[ctype] += 1
        qb_counter[qb] += 1
        length_chars.append(len(text))
        length_tokens.append(len(text.split()))
        low = text.lower()
        if any(w in low for w in ('risk','slash','slashing','penalty','penalties','attack','exploit')):
            riskish += 1
        if NUMBER_PATTERN.search(text):
            numeric += 1
        if len(examples_per_type[ctype]) < 3:
            examples_per_type[ctype].append(text[:140])
    def pct(x):
        return round(100.0 * x / total,2) if total else 0.0
    stats = {
        'total': total,
        'candidateType_counts': {k:{'count':v,'pct':pct(v)} for k,v in ct_counter.most_common()},
        'quality_bucket_counts': {k:{'count':v,'pct':pct(v)} for k,v in qb_counter.most_common()},
        'char_len': {
            'mean': round(statistics.mean(length_chars),2) if length_chars else 0,
            'p50': int(statistics.median(length_chars)) if length_chars else 0,
            'p90': int(sorted(length_chars)[int(0.9*len(length_chars))-1]) if length_chars else 0,
            'min': min(length_chars) if length_chars else 0,
            'max': max(length_chars) if length_chars else 0,
        },
        'token_len_mean': round(statistics.mean(length_tokens),2) if length_tokens else 0,
        'riskish_pct': pct(riskish),
        'numeric_pct': pct(numeric),
        'examples_per_type': examples_per_type,
        'recommendations': []
    }
    # Heuristic recommendations
    if stats['candidateType_counts'] and len(stats['candidateType_counts']) == 1:
        stats['recommendations'].append('All candidateType collapsed to a single bucket; refine inference regex or broaden extraction heuristics.')
    if stats['quality_bucket_counts'] and stats['quality_bucket_counts'].get('vlow',{'pct':0})['pct'] > 70:
        stats['recommendations'].append('Majority very low quality; consider adjusting length / noise filters or merging sentences differently.')
    if stats['riskish_pct'] < 5:
        stats['recommendations'].append('Few risk-like sentences detected; may need targeted crawl of security / risk sections.')
    return stats


def build_parser():
    p = argparse.ArgumentParser(description='Diagnose insight dataset distribution.')
    p.add_argument('--in', dest='inp', required=True, help='Insights JSONL (extraction output)')
    p.add_argument('--detailOut', help='Optional TSV with text, inferredType, qualityBucket')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    stats = summarize(args.inp)
    if args.detailOut:
        import csv
        with open(args.detailOut,'w',encoding='utf-8',newline='') as f:
            w = csv.writer(f, delimiter='\t')
            w.writerow(['candidateType','qualityBucket','textPreview'])
            for ctype, examples in stats['examples_per_type'].items():
                for ex in examples:
                    # quality bucket unknown per-example here (skipped for brevity)
                    w.writerow([ctype,'?',ex])
    sys.stdout.write(json.dumps(stats, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':  # pragma: no cover
    main()
