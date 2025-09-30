from __future__ import annotations
"""Stratified train/dev/test splitter for labeled insights.

Input: JSONL with at least fields {text,label}
Output: three JSONL files written to --outDir: train.jsonl, dev.jsonl, test.jsonl

Example:
  python src/cli/split_dataset.py --data data/labeled.jsonl --outDir data/splits \
      --train 0.7 --dev 0.15 --test 0.15 --seed 42

If ratios do not sum to 1.0 exactly they are normalized.
Stratification ensures each label keeps roughly the same proportion.

Edge handling:
 - If a class has fewer than 3 items, it will allocate at least 1 to train; the rest
   are distributed to dev then test if possible.
"""
import argparse, json, random, math, os, sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List

LABELS = ["Advantage","Risk","Neutral"]

def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def write_jsonl(path: Path, rows):
    with path.open('w',encoding='utf-8') as w:
        for r in rows:
            w.write(json.dumps(r, ensure_ascii=False) + "\n")

def stratified_split(rows: List[Dict], ratios, seed: int):
    random.seed(seed)
    train_r, dev_r, test_r = ratios
    total_r = train_r + dev_r + test_r
    train_r, dev_r, test_r = train_r/total_r, dev_r/total_r, test_r/total_r
    by_label = defaultdict(list)
    for r in rows:
        l = r.get('label')
        if l in LABELS and r.get('text'):
            by_label[l].append(r)
    train, dev, test = [], [], []
    for lab, items in by_label.items():
        random.shuffle(items)
        n = len(items)
        if n == 1:
            train.extend(items)
            continue
        if n == 2:
            train.append(items[0]); dev.append(items[1]); continue
        n_train = max(1, int(round(n * train_r)))
        n_dev = max(1, int(round(n * dev_r)))
        if n_train + n_dev >= n:  # fix overflow
            n_dev = max(1, n - n_train - 1)
        n_test = n - n_train - n_dev
        if n_test == 0 and n >= 3:
            n_test = 1; n_dev = max(1, n_dev - 1)
        train.extend(items[:n_train])
        dev.extend(items[n_train:n_train+n_dev])
        test.extend(items[n_train+n_dev:])
    return train, dev, test

def build_parser():
    a = argparse.ArgumentParser(description='Stratified split of labeled dataset into train/dev/test JSONL files.')
    a.add_argument('--data', required=True)
    a.add_argument('--outDir', required=True)
    a.add_argument('--train', type=float, default=0.7)
    a.add_argument('--dev', type=float, default=0.15)
    a.add_argument('--test', type=float, default=0.15)
    a.add_argument('--seed', type=int, default=42)
    return a

def main(argv=None):
    args = build_parser().parse_args(argv)
    rows = [r for r in iter_jsonl(args.data) if r.get('text') and r.get('label') in LABELS]
    if not rows:
        print('No valid labeled rows found.', file=sys.stderr); sys.exit(1)
    train, dev, test = stratified_split(rows, (args.train,args.dev,args.test), args.seed)
    out_dir = Path(args.outDir); out_dir.mkdir(parents=True, exist_ok=True)
    write_jsonl(out_dir / 'train.jsonl', train)
    write_jsonl(out_dir / 'dev.jsonl', dev)
    write_jsonl(out_dir / 'test.jsonl', test)
    summary = {
        'counts': {
            'train': len(train), 'dev': len(dev), 'test': len(test), 'total': len(rows)
        }
    }
    print(json.dumps(summary, indent=2))

if __name__ == '__main__':  # pragma: no cover
    main()
