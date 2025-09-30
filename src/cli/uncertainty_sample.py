from __future__ import annotations
"""Select next batch of unlabeled insights via uncertainty sampling.

Strategy options:
  entropy: highest Shannon entropy of probability distribution
  margin: smallest difference between top-1 and top-2 probabilities
  least_confidence: lowest top probability (1 - max_p)

Example:
  python src/cli/uncertainty_sample.py --in data/eigenlayer.insights.jsonl \
      --labeled data/seed_labeled.jsonl --modelDir models/distilbert_meta_demo \
      --out data/batch_uncertainty.v1.jsonl --k 75 --strategy entropy

Notes:
 - Excludes any text already present (exact match) in the labeled file.
 - Preserves provenance if present; otherwise sets provenance='scraped'.
 - Adds fields: probs, entropy, margin, topProb, strategyScore, sample_phase='uncertainty'.
 - Applies temperature calibration if calibration.json exists in modelDir.
"""
import argparse, json, math, os, sys, random
from pathlib import Path
from typing import Dict, List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.backends import load_backend

def iter_jsonl(path: str):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def load_labeled_texts(path: str) -> set[str]:
    if not path or not os.path.exists(path):
        return set()
    s = set()
    for obj in iter_jsonl(path):
        t = obj.get('text')
        if t: s.add(t)
    return s

def entropy(probs: Dict[str,float]) -> float:
    return -sum(p * math.log(p + 1e-12) for p in probs.values())

def margin(sorted_probs: List[float]) -> float:
    if len(sorted_probs) < 2: return 1.0
    return sorted_probs[0] - sorted_probs[1]

def apply_temperature(raw: Dict[str,float], temperature: float | None) -> Dict[str,float]:
    if not temperature or temperature in (1.0,):
        return raw
    # Convert Bernoulli-style probs to logits then resoftmax across labels
    labs = list(raw.keys())
    vals = [min(max(raw[l], 1e-9), 1-1e-9) for l in labs]
    logits = [math.log(v) - math.log(1-v) for v in vals]
    scaled = [lg / temperature for lg in logits]
    m = max(scaled)
    exps = [math.exp(s - m) for s in scaled]
    z = sum(exps) or 1.0
    return {labs[i]: exps[i]/z for i in range(len(labs))}

def build_parser():
    p = argparse.ArgumentParser(description='Uncertainty sampling for next labeling batch.')
    p.add_argument('--in', dest='inp', required=True, help='Unlabeled insights JSONL (extraction output)')
    p.add_argument('--labeled', required=True, help='Already labeled JSONL to exclude (text match)')
    p.add_argument('--modelDir', required=True, help='Directory with trained model backend')
    p.add_argument('--out', required=True, help='Output JSONL for selected batch')
    p.add_argument('--k', type=int, default=80, help='Number of samples to select')
    p.add_argument('--strategy', choices=['entropy','margin','least_confidence'], default='entropy')
    p.add_argument('--seed', type=int, default=42)
    return p

def main(argv=None):
    args = build_parser().parse_args(argv)
    random.seed(args.seed)
    labeled_texts = load_labeled_texts(args.labeled)
    backend = load_backend(args.modelDir)
    calib_path = Path(args.modelDir) / 'calibration.json'
    temperature = None
    if calib_path.exists():
        try:
            data = json.loads(calib_path.read_text(encoding='utf-8'))
            temperature = float(data.get('temperature')) if data.get('temperature') else None
        except Exception:
            temperature = None
    candidates = []
    for obj in iter_jsonl(args.inp):
        text = obj.get('text')
        if not text or text in labeled_texts:
            continue
        raw_probs = backend.predict_proba([text])[0]
        probs = apply_temperature(raw_probs, temperature)
        # order by descending probability
        sorted_vals = sorted(probs.values(), reverse=True)
        ent = entropy(probs)
        marg = margin(sorted_vals)
        top_prob = sorted_vals[0] if sorted_vals else 0.0
        if args.strategy == 'entropy':
            score = ent
        elif args.strategy == 'margin':
            score = -marg  # smaller margin -> higher score
        else:  # least_confidence
            score = 1 - top_prob
        candidates.append({
            'text': text,
            'sourceUrl': obj.get('sourceUrl'),
            'candidateType': obj.get('candidateType','other'),
            'qualityScore': obj.get('qualityScore'),
            'provenance': obj.get('provenance','scraped'),
            'probs': probs,
            'entropy': round(ent,4),
            'margin': round(marg,4),
            'topProb': round(top_prob,4),
            'strategyScore': round(score,4),
            'strategy': args.strategy,
            'sample_phase': 'uncertainty'
        })
    # sort by descending strategyScore
    candidates.sort(key=lambda r: r['strategyScore'], reverse=True)
    selected = candidates[:args.k]
    with open(args.out,'w',encoding='utf-8') as w:
        for r in selected:
            w.write(json.dumps(r, ensure_ascii=False) + '\n')
    stats = {
        'total_candidates': len(candidates),
        'selected': len(selected),
        'strategy': args.strategy,
        'temperature': temperature,
    }
    sys.stdout.write(json.dumps(stats, indent=2) + '\n')

if __name__ == '__main__':  # pragma: no cover
    main()
