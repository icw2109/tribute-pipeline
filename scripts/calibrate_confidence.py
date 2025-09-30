#!/usr/bin/env python
"""Calibrate confidence scores using either temperature scaling (single scalar)
or isotonic regression (non-parametric) based on a labeled dev set.

Usage:
  python scripts/calibrate_confidence.py --pred out/insights_classified.jsonl --gold data/dev.jsonl --method temperature --out out/calibration.json

The script outputs a JSON with calibration parameters and recalculated ECE.
"""
import argparse, json, math
from pathlib import Path
from statistics import mean

try:
    from sklearn.isotonic import IsotonicRegression
except Exception:
    IsotonicRegression = None


def load_jsonl(p: Path):
    rows=[]
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip();
            if not line: continue
            try: rows.append(json.loads(line))
            except: pass
    return rows


def expected_calibration_error(gold, pred, conf, bins=10):
    bin_tot=[0]*bins; bin_conf=[0.0]*bins; bin_acc=[0.0]*bins
    for g,p,c in zip(gold,pred,conf):
        if not isinstance(c,(int,float)): continue
        b=min(bins-1, int(float(c)*bins))
        bin_tot[b]+=1; bin_conf[b]+=c; bin_acc[b]+= 1.0 if g==p else 0.0
    ece=0.0; total=sum(bin_tot) or 1
    for i in range(bins):
        if bin_tot[i]==0: continue
        ece += (bin_tot[i]/total) * abs((bin_conf[i]/bin_tot[i]) - (bin_acc[i]/bin_tot[i]))
    return round(ece,4)


def temperature_scale(confidences, gold, pred):
    # Simple 1D optimization: search T in grid minimizing NLL (treat confidence as p(correct)).
    # Guard: ensure conf in (0,1)
    eps=1e-6
    c=[min(max(x,eps),1-eps) for x in confidences]
    correct=[1.0 if g==p else 0.0 for g,p in zip(gold,pred)]
    # Convert to logits: log(p/(1-p))
    import math
    logits=[math.log(p/(1-p)) for p in c]
    best_T=1.0; best_nll=1e9
    for T in [0.25,0.5,0.75,1.0,1.25,1.5,1.75,2.0,2.5,3.0]:
        nll=0.0
        for logit,y in zip(logits,correct):
            p=1/(1+math.exp(-logit/T))
            p=min(max(p,eps),1-eps)
            nll += - (y*math.log(p) + (1-y)*math.log(1-p))
        if nll < best_nll:
            best_nll=nll; best_T=T
    scaled=[1/(1+math.exp(-l/best_T)) for l in logits]
    return best_T, scaled


def isotonic_scale(confidences, gold, pred):
    if IsotonicRegression is None:
        raise SystemExit('sklearn not installed for isotonic regression')
    # Use correctness indicator vs raw confidence
    correct=[1.0 if g==p else 0.0 for g,p in zip(gold,pred)]
    ir=IsotonicRegression(out_of_bounds='clip')
    scaled=ir.fit_transform(confidences, correct)
    return {'y_min':float(min(correct)), 'y_max':float(max(correct))}, list(map(float,scaled))


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--pred', required=True)
    ap.add_argument('--gold', required=True)
    ap.add_argument('--method', choices=['temperature','isotonic'], default='temperature')
    ap.add_argument('--out', required=True)
    ap.add_argument('--bins', type=int, default=10)
    args=ap.parse_args()

    pred_rows=load_jsonl(Path(args.pred))
    gold_rows=load_jsonl(Path(args.gold))
    pred_map={r.get('text'): r for r in pred_rows if 'text' in r}

    gold_labels=[]; pred_labels=[]; confidences=[]
    for g in gold_rows:
        txt=g.get('text'); gl=g.get('label')
        if txt in pred_map:
            gold_labels.append(gl)
            pred_labels.append(pred_map[txt].get('label'))
            confidences.append(pred_map[txt].get('confidence'))

    if not gold_labels:
        raise SystemExit('No overlapping examples between gold and predictions')

    before_ece = expected_calibration_error(gold_labels,pred_labels,confidences,bins=args.bins)

    if args.method=='temperature':
        T, scaled = temperature_scale(confidences, gold_labels, pred_labels)
        after_ece = expected_calibration_error(gold_labels,pred_labels,scaled,bins=args.bins)
        calib={'method':'temperature','T':T,'before_ece':before_ece,'after_ece':after_ece}
    else:
        meta, scaled = isotonic_scale(confidences,gold_labels,pred_labels)
        after_ece = expected_calibration_error(gold_labels,pred_labels,scaled,bins=args.bins)
        calib={'method':'isotonic','meta':meta,'before_ece':before_ece,'after_ece':after_ece}

    out_path=Path(args.out)
    out_path.write_text(json.dumps(calib, indent=2), encoding='utf-8')
    print(json.dumps(calib, indent=2))

if __name__=='__main__':
    main()
