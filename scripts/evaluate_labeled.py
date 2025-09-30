#!/usr/bin/env python
"""Evaluation harness for classified insights against a gold JSONL file.

Gold file schema expectation (minimum):
  {"text": str, "label": "Advantage|Risk|Neutral"}
Prediction file: output from classify.py (must contain 'label').

Metrics:
  - Per-class precision, recall, F1
  - Macro F1
  - Support counts
  - Confusion matrix (labels ordered Advantage,Risk,Neutral)
  - Optional Expected Calibration Error (ECE) if confidence field present

Usage:
  python scripts/evaluate_labeled.py --gold data/labeled_test.jsonl --pred out/insights_classified.jsonl --ece-bins 10
"""
import argparse, json, math
from pathlib import Path
from collections import Counter, defaultdict

LABELS = ["Advantage", "Risk", "Neutral"]


def load_jsonl(p: Path):
    rows = []
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                rows.append(json.loads(line))
            except Exception:
                pass
    return rows


def confusion_matrix(gold, pred):
    idx = {l:i for i,l in enumerate(LABELS)}
    m = [[0]*len(LABELS) for _ in LABELS]
    for g,p in zip(gold, pred):
        if g in idx and p in idx:
            m[idx[g]][idx[p]] += 1
    return m


def precision_recall_f1(cm):
    metrics = {}
    for i,l in enumerate(LABELS):
        tp = cm[i][i]
        fp = sum(cm[r][i] for r in range(len(LABELS)) if r!=i)
        fn = sum(cm[i][c] for c in range(len(LABELS)) if c!=i)
        prec = tp / (tp+fp) if (tp+fp)>0 else 0.0
        rec = tp / (tp+fn) if (tp+fn)>0 else 0.0
        f1 = 2*prec*rec/(prec+rec) if (prec+rec)>0 else 0.0
        metrics[l] = {
            'precision': round(prec,3),
            'recall': round(rec,3),
            'f1': round(f1,3),
            'support': sum(cm[i])
        }
    macro_f1 = round(sum(m['f1'] for m in metrics.values())/len(LABELS),3)
    return metrics, macro_f1


def expected_calibration_error(gold_labels, pred_labels, confidences, bins=10):
    # Treat correct=1 else 0; measure difference between avg confidence and accuracy in bin.
    bin_totals = [0]*bins
    bin_conf_sum = [0.0]*bins
    bin_acc_sum = [0.0]*bins
    for g,p,c in zip(gold_labels, pred_labels, confidences):
        if not isinstance(c,(int,float)): continue
        b = min(bins-1, int(float(c)*bins))
        bin_totals[b]+=1
        bin_conf_sum[b]+=float(c)
        bin_acc_sum[b]+= 1.0 if g==p else 0.0
    ece = 0.0
    details=[]
    total = sum(bin_totals) or 1
    for i in range(bins):
        if bin_totals[i]==0:
            details.append({'bin':i,'range':f"{i/bins:.2f}-{(i+1)/bins:.2f}", 'count':0})
            continue
        avg_conf = bin_conf_sum[i]/bin_totals[i]
        acc = bin_acc_sum[i]/bin_totals[i]
        weight = bin_totals[i]/total
        ece += weight * abs(avg_conf-acc)
        details.append({'bin':i,'range':f"{i/bins:.2f}-{(i+1)/bins:.2f}", 'count':bin_totals[i], 'avg_conf':round(avg_conf,3), 'acc':round(acc,3)})
    return round(ece,4), details


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--gold', required=True)
    ap.add_argument('--pred', required=True)
    ap.add_argument('--ece-bins', type=int, default=10)
    args = ap.parse_args()

    gold_rows = load_jsonl(Path(args.gold))
    pred_rows = load_jsonl(Path(args.pred))

    # Align predictions to gold by exact text match (dict map) for simplicity.
    pred_map = {r.get('text'): r for r in pred_rows if 'text' in r and 'label' in r}

    gold_labels=[]; pred_labels=[]; confidences=[]
    missing=0
    for g in gold_rows:
        txt = g.get('text'); gl = g.get('label')
        if txt in pred_map:
            gold_labels.append(gl)
            pred_labels.append(pred_map[txt].get('label'))
            confidences.append(pred_map[txt].get('confidence'))
        else:
            missing+=1

    cm = confusion_matrix(gold_labels, pred_labels)
    per_class, macro_f1 = precision_recall_f1(cm)
    ece, ece_bins = expected_calibration_error(gold_labels, pred_labels, confidences, bins=args.ece_bins)

    out = {
        'counts': {
            'gold_total': len(gold_rows),
            'evaluated': len(gold_labels),
            'missing_predictions': missing
        },
        'macro_f1': macro_f1,
        'per_class': per_class,
        'confusion_matrix': {
            'labels': LABELS,
            'matrix': cm
        },
        'ece': ece,
        'ece_bins': ece_bins
    }
    print(json.dumps(out, indent=2))

if __name__ == '__main__':
    main()
