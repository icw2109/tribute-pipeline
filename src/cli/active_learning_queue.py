from __future__ import annotations
"""Generate an active learning queue from a classified insights JSONL.

Ranking criteria (composite score):
 1. Probability entropy (higher -> more uncertain)
 2. Disagreement: heuristic vs final label (1 if different else 0)
 3. NLI disagreement: if nli label differs from final (0.5 boost)

Score = entropy + 0.6*heuristic_disagree + 0.4*nli_disagree

Output: top N records ordered by descending score with fields:
  text, label, modelProbs, ruleStrength, finalConfidence, score

Usage:
  python src/cli/active_learning_queue.py --in out/ensemble.labeled.v2.jsonl --out out/active_queue.jsonl --top 30
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

def entropy(probs: Dict[str,float]) -> float:
    if not probs:
        return 0.0
    total = sum(probs.values()) or 1.0
    e = 0.0
    for p in probs.values():
        if p <= 0: continue
        p/=total
        e -= p*math.log(p,2)
    return e

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', dest='out', required=True)
    ap.add_argument('--top', type=int, default=50)
    args = ap.parse_args()

    items = []
    for rec in iter_jsonl(args.inp):
        probs = rec.get('modelProbs') or {}
        e = entropy(probs)
        heur_label = 'Unknown'
        prov = rec.get('classificationProvenance') or []
        # heuristic label is ambiguous; approximate via signals + ruleStrength: treat signals presence & ruleStrength>0.75 as that label
        heur_label = rec.get('label') if 'heuristic' in prov and len(prov)==1 else None
        final_label = rec.get('label')
        heuristic_disagree = 0
        if heur_label and heur_label != final_label:
            heuristic_disagree = 1
        nli = rec.get('nli') or {}
        nli_disagree = 0.0
        if nli and nli.get('label') and nli.get('label') != final_label:
            nli_disagree = 0.5
        score = e + 0.6*heuristic_disagree + 0.4*nli_disagree
        items.append({
            'text': rec.get('text'),
            'label': final_label,
            'modelProbs': probs,
            'ruleStrength': rec.get('ruleStrength'),
            'finalConfidence': rec.get('finalConfidence'),
            'entropy': round(e,3),
            'score': round(score,3)
        })

    items.sort(key=lambda x: x['score'], reverse=True)
    top_items = items[:args.top]
    with open(args.out,'w',encoding='utf-8') as w:
        for it in top_items:
            w.write(json.dumps(it, ensure_ascii=False) + '\n')
    print(json.dumps({'input': args.inp, 'written': len(top_items), 'out': args.out}))

if __name__ == '__main__':
    main()
