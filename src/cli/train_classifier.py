from __future__ import annotations
"""Train Tier1 classical classifier (logistic regression) over insights.

Input JSONL must contain objects with fields: text, label.
Splits into train/dev (80/20) to report preliminary metrics. For a real
deployment you'd maintain a curated dev set, but this is a bootstrap utility.
"""
import argparse, json, random, time, sys, os
from pathlib import Path
from collections import Counter
from typing import List

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.lexicon import DEFAULT_LEXICON
from insights.backends import train_backend, save_backend, LABELS
from insights.calibration import fit_temperature


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


def build_parser():
    p = argparse.ArgumentParser(description='Train classifier (supports external splits).')
    p.add_argument('--data', help='(Deprecated when using --trainFile/--devFile) Single JSONL to random-split 80/20')
    p.add_argument('--trainFile', help='Train split JSONL')
    p.add_argument('--devFile', help='Dev/validation split JSONL')
    p.add_argument('--testFile', help='Test split JSONL (for final evaluation)')
    p.add_argument('--outDir', required=True, help='Directory to write model artifacts')
    p.add_argument('--seed', type=int, default=42)
    p.add_argument('--maxFeatures', type=int, default=20000, help='Max features for tfidf backend')
    p.add_argument('--backend', choices=['tfidf','hashing','distilbert'], default='tfidf', help='Model backend implementation')
    p.add_argument('--hashFeatures', type=int, default=2**18, help='Number of hashing features (hashing backend)')
    # DistilBERT backend specific
    p.add_argument('--hfModel', default='distilbert-base-uncased', help='HF model name for distilbert backend')
    p.add_argument('--embedBatchSize', type=int, default=16, help='Embedding batch size for distilbert backend')
    p.add_argument('--maxSeqLen', type=int, default=256, help='Max sequence length for transformer embedding')
    p.add_argument('--pooling', choices=['cls','mean'], default='cls', help='Pooling strategy for transformer embedding')
    p.add_argument('--noDense', action='store_true', help='Do not concatenate handcrafted dense features with transformer embeddings')
    p.add_argument('--calibrate', action='store_true', help='Fit temperature scaling on dev split and save calibration.json')
    p.add_argument('--useMetadata', action='store_true', help='If present and inputs have candidateType/qualityScore fields, embed them as metadata prefix tokens for classical models')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    random.seed(args.seed)

    def load_labeled(path: str):
        t_list: List[str] = []
        l_list: List[str] = []
        for obj in iter_jsonl(path):
            t = obj.get('text'); l = obj.get('label')
            if not t or not l: continue
            if l not in LABELS: continue
            if args.useMetadata:
                ctype = obj.get('candidateType')
                q = obj.get('qualityScore')
                if ctype is not None or q is not None:
                    meta = {"candidateType": ctype or 'other', "qualityScore": q if isinstance(q,(int,float)) else 0.0}
                    # Prepend a META::header then newline + text; backends will convert to tokens
                    import json as _json
                    t = f"META::{_json.dumps(meta, separators=(',',':'))}\n{t}"
            t_list.append(t); l_list.append(l)
        return t_list, l_list

    if args.trainFile and args.devFile:
        train_texts, train_labels = load_labeled(args.trainFile)
        dev_texts, dev_labels = load_labeled(args.devFile)
        if not train_texts:
            print('Train split empty', file=sys.stderr); sys.exit(1)
        if not dev_texts:
            print('Dev split empty', file=sys.stderr); sys.exit(1)
        test_texts: List[str] = []
        test_labels: List[str] = []
        if args.testFile:
            test_texts, test_labels = load_labeled(args.testFile)
    else:
        if not args.data:
            print('Provide --data or explicit --trainFile/--devFile', file=sys.stderr); sys.exit(1)
        texts: List[str] = []
        labels: List[str] = []
        for obj in iter_jsonl(args.data):
            t = obj.get('text'); l = obj.get('label')
            if not t or not l: continue
            if l not in LABELS: continue
            texts.append(t); labels.append(l)
        if not texts:
            print('No training data found', file=sys.stderr)
            sys.exit(1)
        idx = list(range(len(texts)))
        random.shuffle(idx)
        split = int(0.8 * len(idx))
        train_idx, dev_idx = idx[:split], idx[split:]
        train_texts = [texts[i] for i in train_idx]
        train_labels = [labels[i] for i in train_idx]
        dev_texts = [texts[i] for i in dev_idx]
        dev_labels = [labels[i] for i in dev_idx]
        test_texts = []
        test_labels = []
    start = time.time()
    if args.backend == 'tfidf':
        backend = train_backend('tfidf', train_texts, train_labels, DEFAULT_LEXICON, max_features=args.maxFeatures)
    elif args.backend == 'hashing':
        backend = train_backend('hashing', train_texts, train_labels, DEFAULT_LEXICON, n_features=args.hashFeatures)
    else:  # distilbert
        backend = train_backend('distilbert', train_texts, train_labels, DEFAULT_LEXICON,
                                hf_model=args.hfModel,
                                embed_batch_size=args.embedBatchSize,
                                max_seq_len=args.maxSeqLen,
                                pooling=args.pooling,
                                use_dense=(not args.noDense))
    elapsed = time.time() - start
    # Quick dev evaluation
    dev_probs = backend.predict_proba(dev_texts)
    # pick highest probability label
    pred_labels = []
    for p in dev_probs:
        pred_labels.append(max(p.items(), key=lambda kv: kv[1])[0])
    # metrics
    from collections import defaultdict
    cm = defaultdict(lambda: defaultdict(int))
    for true, pred in zip(dev_labels, pred_labels):
        cm[true][pred] += 1
    def prf(lab: str):
        tp = cm[lab][lab]
        fp = sum(cm[o][lab] for o in LABELS if o != lab)
        fn = sum(cm[lab][o] for o in LABELS if o != lab)
        prec = tp/(tp+fp+1e-9); rec = tp/(tp+fn+1e-9)
        f1 = 2*prec*rec/(prec+rec+1e-9) if (prec+rec)>0 else 0
        return {'precision': round(prec,3), 'recall': round(rec,3), 'f1': round(f1,3)}
    per_class = {lab: prf(lab) for lab in LABELS}
    macro_f1 = round(sum(v['f1'] for v in per_class.values())/len(LABELS),3)
    meta = {
        'train_size': len(train_texts),
        'dev_size': len(dev_texts),
        'class_distribution': Counter(train_labels),
        'macro_f1_dev': macro_f1,
        'per_class_dev': per_class,
        'train_seconds': round(elapsed,3)
    }
    save_backend(backend, args.outDir, meta)
    # Optional calibration
    if args.calibrate and dev_texts:
        raw_probs = backend.predict_proba(dev_texts)
        temp_cal = fit_temperature(raw_probs, dev_labels)
        calib_path = Path(args.outDir) / 'calibration.json'
        calib_path.write_text(json.dumps({'temperature': temp_cal.temperature, 'fitted_on': 'dev_split', 'dev_size': len(dev_texts)}, indent=2), encoding='utf-8')

    # Optional test evaluation
    test_report = None
    if args.testFile and 'test_texts' in locals() and test_texts:
        test_probs = backend.predict_proba(test_texts)
        pred_test = [max(p.items(), key=lambda kv: kv[1])[0] for p in test_probs]
        from collections import defaultdict as _dd
        cm_t = _dd(lambda: _dd(int))
        for tr, pr in zip(test_labels, pred_test):
            cm_t[tr][pr] += 1
        def _prf_test(lab: str):
            tp = cm_t[lab][lab]; fp = sum(cm_t[o][lab] for o in LABELS if o!=lab); fn = sum(cm_t[lab][o] for o in LABELS if o!=lab)
            prec = tp/(tp+fp+1e-9); rec = tp/(tp+fn+1e-9)
            f1 = 2*prec*rec/(prec+rec+1e-9) if (prec+rec)>0 else 0
            return {'precision': round(prec,3), 'recall': round(rec,3), 'f1': round(f1,3)}
        per_class_test = {lab: _prf_test(lab) for lab in LABELS}
        macro_f1_test = round(sum(v['f1'] for v in per_class_test.values())/len(LABELS),3)
        test_report = {'macro_f1_test': macro_f1_test, 'per_class_test': per_class_test}

    output = {'saved': args.outDir, 'macro_f1_dev': macro_f1, 'train_seconds': round(elapsed,3), 'calibrated': bool(args.calibrate)}
    if test_report:
        output.update(test_report)
    print(json.dumps(output, indent=2))


if __name__ == '__main__':  # pragma: no cover
    main()
