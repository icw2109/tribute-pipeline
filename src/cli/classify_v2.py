from __future__ import annotations
"""Minimal classification CLI for Part 3 spec.

Input: enriched insights JSONL containing at least {"text": ...}
Output: insights_classified.jsonl with records:
  {text, label, labelTag, rationale, confidence}

Usage:
  python -m cli.classify_v2 --in data/eigenlayer.insights.enriched.jsonl --out out/insights_classified.jsonl --model models/selftrain_embed
"""
import argparse, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from insights.simple_classifier import SimpleClassifier
import warnings as _warnings
_warnings.warn(
    'cli.classify_v2 is deprecated; please use cli.classify (unified pipeline) instead.',
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
    ap.add_argument('--in', dest='inp', required=True, help='Input enriched insights JSONL')
    ap.add_argument('--out', dest='out', required=True, help='Output classified JSONL path')
    ap.add_argument('--model', dest='model', help='Optional self-train model directory')
    ap.add_argument('--strongThreshold', type=float, default=0.75, help='Heuristic strength above which model is skipped')
    args = ap.parse_args()

    clf = SimpleClassifier(self_train_model_path=args.model, strong_threshold=args.strongThreshold)
    count = 0
    with open(args.out,'w',encoding='utf-8') as w:
        for rec in iter_jsonl(args.inp):
            txt = rec.get('text')
            if not txt:
                continue
            out = clf.classify(txt)
            # ensure required fields retained
            w.write(json.dumps({
                'text': txt,
                **out
            }, ensure_ascii=False) + '\n')
            count += 1
    print(json.dumps({'processed': count, 'out': args.out}))

if __name__ == '__main__':
    main()