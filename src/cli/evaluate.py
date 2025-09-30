from __future__ import annotations
"""Evaluate one or more trained model backends on a labeled JSONL dataset.

Usage:
  python -m cli.evaluate --data labeled.jsonl --modelDir path/to/model
  python -m cli.evaluate --data labeled.jsonl --modelDir path/to/tfidf --compare path/to/hashing

Outputs JSON metrics (macro F1, per-class precision/recall/F1, confusion matrix, latency stats).
"""
import argparse, json, time, os, sys
from pathlib import Path
from typing import List, Dict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.backends import load_backend, LABELS
from insights.lexicon import DEFAULT_LEXICON


def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_dataset(path: str):
    texts: List[str] = []
    labels: List[str] = []
    for obj in iter_jsonl(path):
        t = obj.get('text'); l = obj.get('label')
        if not t or not l: continue
        if l not in LABELS: continue
        texts.append(t); labels.append(l)
    return texts, labels


def evaluate_backend(backend, texts: List[str], labels: List[str]):
    start = time.time()
    probs = backend.predict_proba(texts, DEFAULT_LEXICON)
    infer_s = time.time() - start
    preds = []
    for p in probs:
        preds.append(max(p.items(), key=lambda kv: kv[1])[0])
    # confusion matrix
    cm = {a:{b:0 for b in LABELS} for a in LABELS}
    for gold, pred in zip(labels, preds):
        cm[gold][pred] += 1
    eps = 1e-9
    per_class = {}
    for lab in LABELS:
        tp = cm[lab][lab]
        fp = sum(cm[o][lab] for o in LABELS if o!=lab)
        fn = sum(cm[lab][o] for o in LABELS if o!=lab)
        prec = tp/(tp+fp+eps)
        rec = tp/(tp+fn+eps)
        f1 = 2*prec*rec/(prec+rec+eps) if (prec+rec)>0 else 0
        per_class[lab] = {'precision': round(prec,3), 'recall': round(rec,3), 'f1': round(f1,3)}
    macro_f1 = round(sum(v['f1'] for v in per_class.values())/len(LABELS),3)
    return {
        'macro_f1': macro_f1,
        'per_class': per_class,
        'confusion_matrix': cm,
        'samples': len(texts),
        'total_seconds': round(infer_s,3),
        'avg_ms_per_sample': round((infer_s/len(texts))*1000,3) if texts else None,
        'backend': getattr(backend,'backend_name','unknown'),
    }


def build_parser():
    p = argparse.ArgumentParser(description='Evaluate trained backend on labeled data.')
    p.add_argument('--data', required=True, help='Labeled JSONL (text,label)')
    p.add_argument('--modelDir', required=True, help='Primary model directory')
    p.add_argument('--compare', help='Optional second model directory to compare')
    p.add_argument('--out', help='Write metrics JSON to file (else stdout)')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    texts, labels = load_dataset(args.data)
    if not texts:
        print('No valid labeled examples', file=sys.stderr)
        sys.exit(1)
    primary = load_backend(args.modelDir)
    primary_metrics = evaluate_backend(primary, texts, labels)
    result = {'primary': primary_metrics}
    if args.compare:
        comp = load_backend(args.compare)
        comp_metrics = evaluate_backend(comp, texts, labels)
        result['compare'] = comp_metrics
    out_json = json.dumps(result, indent=2)
    if args.out:
        Path(args.out).write_text(out_json, encoding='utf-8')
    else:
        print(out_json)

if __name__ == '__main__':  # pragma: no cover
    main()
