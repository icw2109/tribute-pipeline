from __future__ import annotations
"""Batch classification using ensemble strategy.

Reads JSONL with at least 'text'. Writes enriched JSONL with final label/tag and provenance fields.

Example:
  python -m cli.ensemble_classify --in data/eigenlayer.insights.enriched.jsonl --out out/ensemble.labeled.jsonl --model models/selftrain --enableZeroShot
"""
import argparse, json, sys
from pathlib import Path
import os

# Ensure 'src' path for package resolution (avoid picking cli.insights on some setups)
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from insights.ensemble import EnsembleClassifier
import warnings as _warnings
_warnings.warn(
    'cli.ensemble_classify is deprecated; use cli.classify with --enable-self-train/--enable-zero-shot config.',
    DeprecationWarning,
    stacklevel=2
)


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
    ap.add_argument('--out', dest='out', required=True)
    ap.add_argument('--model', dest='model', help='Path to self-train model artifacts directory')
    ap.add_argument('--ruleStrong', type=float, default=0.75)
    ap.add_argument('--modelFloor', type=float, default=0.55)
    ap.add_argument('--enableZeroShot', action='store_true')
    ap.add_argument('--zeroShotModel', default='facebook/bart-large-mnli')
    ap.add_argument('--debug', action='store_true', help='Include top feature contributions')
    ap.add_argument('--explainTopK', type=int, default=5, help='Top K features to show when --debug set')
    args = ap.parse_args()

    cfg = {
        'ruleStrongThreshold': args.ruleStrong,
        'modelFloor': args.modelFloor,
        'enableZeroShot': args.enableZeroShot,
        'zeroShotModel': args.zeroShotModel,
    }
    ens = EnsembleClassifier(self_train_model_path=args.model, config=cfg)

    count = 0
    with open(args.out,'w',encoding='utf-8') as w:
        for rec in iter_jsonl(args.inp):
            txt = rec.get('text')
            if not txt:
                continue
            res = ens.classify(txt, debug=args.debug, explain_top_k=args.explainTopK)
            rec.update({
                'label': res['label'],
                'labelTag': res.get('labelTag') or res.get('tag'),
                'tag': res.get('tag'),
                'rationale': res.get('rationale'),
                'strategy': res['strategy'],
                'ruleStrength': res['ruleStrength'],
                'signals': res['signals'],
                'modelProbs': res['modelProbs'],
                'nli': res['nli'],
                'finalConfidence': res.get('finalConfidence'),
                'confidence': res.get('confidence', res.get('finalConfidence')),
                'topFeatures': res.get('topFeatures'),
                'provenance': rec.get('provenance','scraped'),
                'classificationProvenance': res['provenance']
            })
            w.write(json.dumps(rec, ensure_ascii=False) + '\n')
            count += 1
    print(json.dumps({'processed': count, 'out': args.out}))

if __name__ == '__main__':
    main()
