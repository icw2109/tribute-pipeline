from __future__ import annotations
"""Calibration reliability report (ECE + per-bin stats).

Computes reliability data for a trained model on a labeled dataset.
Optionally applies temperature calibration if calibration.json present.

Example:
  python src/cli/calibration_report.py --data data/splits/dev.jsonl \
    --modelDir models/distilbert_v1 --out reports/calibration_dev.json
"""
import argparse, json, sys, os, math
from pathlib import Path
from typing import List, Dict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.backends import load_backend, LABELS


def build_parser():
    p = argparse.ArgumentParser(description='Compute calibration reliability (ECE) for model.')
    p.add_argument('--data', required=True, help='Labeled JSONL (text,label)')
    p.add_argument('--modelDir', required=True)
    p.add_argument('--bins', type=int, default=10)
    p.add_argument('--out', required=True)
    return p


def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip();
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_labeled(path: str):
    texts=[]; labels=[]
    for obj in iter_jsonl(path):
        t=obj.get('text'); l=obj.get('label')
        if t and l in LABELS:
            texts.append(t); labels.append(l)
    return texts, labels


def apply_temperature(probs_list: List[Dict[str,float]], T: float):
    if abs(T-1.0) < 1e-6:
        return probs_list
    out=[]
    import math as _m
    for row in probs_list:
        labs=list(row.keys())
        eps=1e-12
        vals=[min(max(row[l],eps),1-eps) for l in labs]
        logits=[_m.log(v)-_m.log(1-v) for v in vals]
        scaled=[lg/T for lg in logits]
        m=max(scaled); exps=[_m.exp(s-m) for s in scaled]; z=sum(exps) or 1.0
        out.append({labs[i]: exps[i]/z for i in range(len(labs))})
    return out


def compute_ece(pred_labels: List[str], probs: List[Dict[str,float]], true_labels: List[str], bins: int):
    # Using max-prob bucket ECE
    assert len(pred_labels)==len(true_labels)==len(probs)
    n=len(pred_labels)
    bucket_tot=[0]*bins; bucket_correct=[0]*bins; bucket_conf=[0.0]*bins
    for pl, tl, pr in zip(pred_labels, true_labels, probs):
        max_p = max(pr.values())
        b = min(bins-1, int(max_p * bins))
        bucket_tot[b]+=1
        bucket_conf[b]+=max_p
        bucket_correct[b]+=1 if pl==tl else 0
    ece=0.0
    bin_data=[]
    for i in range(bins):
        if bucket_tot[i]==0:
            bin_data.append({'bin':i,'count':0,'confidence':None,'accuracy':None})
            continue
        acc = bucket_correct[i]/bucket_tot[i]
        conf = bucket_conf[i]/bucket_tot[i]
        ece += (bucket_tot[i]/n) * abs(acc-conf)
        bin_data.append({'bin':i,'count':bucket_tot[i],'confidence':round(conf,3),'accuracy':round(acc,3)})
    return round(ece,4), bin_data


def main(argv=None):
    args = build_parser().parse_args(argv)
    texts, labels = load_labeled(args.data)
    if not texts:
        print('No labeled data loaded', file=sys.stderr); sys.exit(1)
    model = load_backend(args.modelDir)
    probs = model.predict_proba(texts)
    # Apply temperature if calibration.json present
    calib_path = Path(args.modelDir)/'calibration.json'
    temperature = 1.0
    if calib_path.exists():
        try:
            c = json.loads(calib_path.read_text(encoding='utf-8'))
            temperature = float(c.get('temperature',1.0))
        except Exception:
            pass
    calibrated_probs = apply_temperature(probs, temperature)
    # Predictions post calibration
    pred_labels = [max(p.items(), key=lambda kv: kv[1])[0] for p in calibrated_probs]
    ece, bins_data = compute_ece(pred_labels, calibrated_probs, labels, args.bins)
    report = {
        'samples': len(texts),
        'bins': args.bins,
        'temperature': temperature,
        'ece': ece,
        'bins_data': bins_data
    }
    Path(args.out).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'ece': ece, 'written': args.out}, indent=2))

if __name__ == '__main__':  # pragma: no cover
    main()
