#!/usr/bin/env python
"""Split a labeled dataset into train/dev/test stratified by label.

Usage:
  python scripts/labeling_split.py --in data/labeling_labeled.jsonl --train-out data/train.jsonl --dev-out data/dev.jsonl --test-out data/test.jsonl --dev 0.3 --test 0.2 --seed 42
"""
import argparse, json, random
from pathlib import Path
from collections import defaultdict


def iter_jsonl(p: Path):
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip();
            if not line: continue
            try: yield json.loads(line)
            except: pass


def write_jsonl(rows, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False)+'\n')


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--train-out', required=True)
    ap.add_argument('--dev-out', required=True)
    ap.add_argument('--test-out', required=True)
    ap.add_argument('--dev', type=float, default=0.25)
    ap.add_argument('--test', type=float, default=0.25)
    ap.add_argument('--seed', type=int, default=42)
    args=ap.parse_args()

    rows=list(iter_jsonl(Path(args.inp)))
    random.seed(args.seed)

    by_label=defaultdict(list)
    for r in rows:
        lab=r.get('label')
        if lab:
            by_label[lab].append(r)

    train=[]; dev=[]; test=[]
    for lab, items in by_label.items():
        random.shuffle(items)
        n=len(items)
        n_test=int(n*args.test)
        n_dev=int(n*args.dev)
        test.extend(items[:n_test])
        dev.extend(items[n_test:n_test+n_dev])
        train.extend(items[n_test+n_dev:])

    write_jsonl(train, Path(args.train_out))
    write_jsonl(dev, Path(args.dev_out))
    write_jsonl(test, Path(args.test_out))

    summary={
        'counts': { 'train': len(train), 'dev': len(dev), 'test': len(test) },
        'per_label': { lab: len(items) for lab, items in by_label.items() },
        'seed': args.seed
    }
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':
    main()
