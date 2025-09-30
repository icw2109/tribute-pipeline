from __future__ import annotations
"""Hybrid threshold tuner.

Sweeps risk and advantage promotion thresholds for hybrid mode using a dev set
and an already-trained model. Outputs best configurations according to:
 - Max Risk Recall (subject to macro F1 >= floor fraction of best macro F1)
 - Best Macro F1

Example:
  python src/cli/threshold_tune.py --dev data/splits/dev.jsonl \
    --modelDir models/distilbert_v1 --truth data/splits/dev.jsonl \
    --riskRange 0.5 0.9 0.05 --advRange 0.5 0.85 0.05
"""
import argparse, json, sys, os, math
from typing import List, Dict, Tuple
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.backends import load_backend
from insights.classify import classify as heuristic_classify
from insights.tag_inference import infer_with_validation

LABELS = ["Advantage","Risk","Neutral"]


def build_parser():
    p = argparse.ArgumentParser(description='Tune hybrid thresholds for risk / advantage promotion.')
    p.add_argument('--dev', required=True, help='Dev JSONL to evaluate')
    p.add_argument('--truth', required=True, help='Truth JSONL (same as --dev if it contains labels)')
    p.add_argument('--modelDir', required=True)
    p.add_argument('--riskRange', nargs=3, type=float, default=[0.5,0.9,0.05], help='start end step for risk threshold sweep')
    p.add_argument('--advRange', nargs=3, type=float, default=[0.5,0.85,0.05], help='start end step for advantage threshold sweep')
    p.add_argument('--f1Floor', type=float, default=0.9, help='Fraction of best macro F1 required when maximizing risk recall')
    p.add_argument('--topK', type=int, default=5, help='Show top K configs by macro F1')
    p.add_argument('--out', help='Write results JSON here')
    return p


def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_truth(path: str):
    m = {}
    for obj in iter_jsonl(path):
        t = obj.get('text'); l = obj.get('label')
        if t and l in LABELS:
            m[t] = l
    return m


def evaluate(records: List[Dict]):
    # Build confusion matrix
    cm = {a:{b:0 for b in LABELS} for a in LABELS}
    for r in records:
        true = r['true']
        pred = r['pred']
        cm[true][pred] += 1
    eps=1e-9
    per_class={}
    for lab in LABELS:
        tp = cm[lab][lab]
        fp = sum(cm[o][lab] for o in LABELS if o!=lab)
        fn = sum(cm[lab][o] for o in LABELS if o!=lab)
        prec = tp/(tp+fp+eps); rec = tp/(tp+fn+eps)
        f1 = 2*prec*rec/(prec+rec+eps) if (prec+rec)>0 else 0
        per_class[lab]={'precision':round(prec,3),'recall':round(rec,3),'f1':round(f1,3)}
    macro_f1 = round(sum(v['f1'] for v in per_class.values())/len(LABELS),3)
    risk_recall = per_class['Risk']['recall']
    return {'macro_f1': macro_f1, 'risk_recall': risk_recall, 'per_class': per_class, 'confusion_matrix': cm}


def run_prediction(texts: List[str], model, risk_thr: float, adv_thr: float):
    # We mimic hybrid logic
    preds=[]
    for t in texts:
        heur = heuristic_classify(t)
        probs = model.predict_proba([t])[0]
        risk_p = probs.get('Risk',0.0)
        adv_p = probs.get('Advantage',0.0)
        label = heur.label
        if label != 'Risk' and risk_p >= risk_thr:
            label = 'Risk'
        elif label == 'Neutral' and adv_p >= adv_thr:
            label = 'Advantage'
        # Tag inference risk precedence check
        tag_inf = infer_with_validation(t)
        if tag_inf.label == 'Risk':
            label = 'Risk'
        preds.append(label)
    return preds


def frange(start: float, end: float, step: float):
    cur = start
    # inclusive of end within a small epsilon
    while cur <= end + 1e-9:
        yield round(cur,4)
        cur += step


def main(argv=None):
    args = build_parser().parse_args(argv)
    truth = load_truth(args.truth)
    dev_texts = []
    dev_labels = []
    for obj in iter_jsonl(args.dev):
        t = obj.get('text'); l = truth.get(obj.get('text'))
        if not t or not l: continue
        dev_texts.append(t); dev_labels.append(l)
    if not dev_texts:
        print('No dev texts loaded', file=sys.stderr); sys.exit(1)
    model = load_backend(args.modelDir)

    results = []
    best_macro = -1.0
    for r_thr in frange(*args.riskRange):
        for a_thr in frange(*args.advRange):
            preds = run_prediction(dev_texts, model, r_thr, a_thr)
            recs = [{'true': tl, 'pred': pl} for tl, pl in zip(dev_labels, preds)]
            metrics = evaluate(recs)
            metrics.update({'risk_threshold': r_thr, 'adv_threshold': a_thr})
            results.append(metrics)
            if metrics['macro_f1'] > best_macro:
                best_macro = metrics['macro_f1']

    # Filter for risk recall objective subject to macro F1 floor
    floor = best_macro * args.f1Floor
    feasible = [m for m in results if m['macro_f1'] >= floor]
    if feasible:
        best_risk = max(feasible, key=lambda m: (m['risk_recall'], m['macro_f1']))
    else:
        best_risk = None
    top_macro = sorted(results, key=lambda m: m['macro_f1'], reverse=True)[:args.topK]

    output = {
        'best_macro': top_macro[0] if top_macro else None,
        'top_macro': top_macro,
        'best_risk_recall': best_risk,
        'floor_macro_f1': floor,
        'total_evals': len(results)
    }
    txt = json.dumps(output, indent=2)
    if args.out:
        Path(args.out).write_text(txt, encoding='utf-8')
    print(txt)

if __name__ == '__main__':  # pragma: no cover
    main()
