from __future__ import annotations
"""Auto-label a seed batch using heuristic or hybrid model for bootstrapping.

IMPORTANT: Output is PROVISIONAL. Human review required before treating as gold.

Modes:
  heuristic (default) - rule-based classifier
  ml - pure model (requires --modelDir)
  hybrid - heuristic + threshold overrides (requires --modelDir)

Adds fields: label, autoLabelConfidence, autoLabelMode, taxonomyVersion.
Can optionally include probs, rationale, and tag inference just like classify.

Usage:
  python src/cli/auto_label.py --in data/seed_batch_balanced.v1.jsonl --out data/seed_labeled.auto.jsonl --mode heuristic
  python src/cli/auto_label.py --in data/seed_batch_balanced.v1.jsonl --out data/seed_labeled.auto.jsonl --mode hybrid --modelDir models/seed_distilbert
"""
import argparse, json, sys, os, time
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.classify import classify as heuristic_classify
from insights.tag_inference import infer_with_validation
from insights.adin_taxonomy import TAXONOMY_VERSION
from insights.rationale import build_rationale as build_tag_rationale
from insights.backends import load_backend


def build_parser():
    p = argparse.ArgumentParser(description='Auto-label provisional dataset.')
    p.add_argument('--in', dest='inp', required=True, help='Input seed batch JSONL (unlabeled)')
    p.add_argument('--out', required=True, help='Output auto-labeled JSONL')
    p.add_argument('--mode', choices=['heuristic','ml','hybrid'], default='heuristic')
    p.add_argument('--modelDir', help='Required for ml or hybrid modes')
    p.add_argument('--hybridRiskThreshold', type=float, default=0.65)
    p.add_argument('--hybridAdvThreshold', type=float, default=0.60)
    p.add_argument('--includeRationale', action='store_true')
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


def main(argv=None):
    args = build_parser().parse_args(argv)
    backend = None
    calibration = None
    if args.mode in ('ml','hybrid'):
        if not args.modelDir:
            print('--modelDir required for ml/hybrid', file=sys.stderr); sys.exit(1)
        backend = load_backend(args.modelDir)
        calib_path = Path(args.modelDir) / 'calibration.json'
        if calib_path.exists():
            try:
                calibration = json.loads(calib_path.read_text(encoding='utf-8'))
            except Exception:
                calibration = None
    start = time.time()
    count = 0
    with open(args.out,'w',encoding='utf-8') as w:
        for obj in iter_jsonl(args.inp):
            text = obj.get('text')
            if not text:
                continue
            heur = heuristic_classify(text)
            model_probs = None
            final_label = heur.label
            if backend:
                raw_probs = backend.predict_proba([text])[0]
                if calibration and calibration.get('temperature') not in (None,1.0):
                    T = float(calibration['temperature'])
                    import math as _m
                    labs = list(raw_probs.keys())
                    vals=[min(max(raw_probs[l],1e-9),1-1e-9) for l in labs]
                    logits=[_m.log(v)-_m.log(1-v) for v in vals]
                    scaled=[lg/ T for lg in logits]
                    m=max(scaled)
                    exps=[_m.exp(s-m) for s in scaled]
                    z=sum(exps) or 1.0
                    model_probs={labs[i]: exps[i]/z for i in range(len(labs))}
                else:
                    model_probs = raw_probs
                if args.mode == 'ml':
                    final_label = max(model_probs.items(), key=lambda kv: kv[1])[0]
                elif args.mode == 'hybrid':
                    risk_p = model_probs.get('Risk',0.0)
                    adv_p = model_probs.get('Advantage',0.0)
                    if final_label != 'Risk' and risk_p >= args.hybridRiskThreshold:
                        final_label = 'Risk'
                    elif final_label == 'Neutral' and adv_p >= args.hybridAdvThreshold:
                        final_label = 'Advantage'
            # Tag inference for taxonomy alignment
            tag_inf = infer_with_validation(text)
            # If tag inference produces Risk but final isn't risk, prefer risk precedence
            if tag_inf.label == 'Risk' and final_label != 'Risk':
                final_label = 'Risk'
            conf = None
            if model_probs:
                conf = model_probs.get(final_label,0.0)
            else:
                base = {'Risk':0.9,'Advantage':0.7,'Neutral':0.4}[final_label]
                conf = base + min(len(heur.signals)*0.05,0.25)
            if conf > 1.0: conf = 1.0
            rec = dict(obj)
            rec['label'] = final_label
            rec['autoLabelMode'] = args.mode
            rec['autoLabelConfidence'] = round(conf,3)
            rec['taxonomyVersion'] = TAXONOMY_VERSION
            rec['labelTag'] = tag_inf.tag
            if model_probs:
                rec['probs'] = model_probs
            if args.includeRationale:
                rec['rationale_auto'] = build_tag_rationale(final_label, tag_inf.tag, heur.signals, [])
            w.write(json.dumps(rec, ensure_ascii=False) + '\n')
            count += 1
    elapsed = time.time() - start
    sys.stdout.write(json.dumps({'count': count, 'seconds': round(elapsed,3), 'items_per_sec': round(count/(elapsed+1e-6),2)}) + '\n')

if __name__ == '__main__':  # pragma: no cover
    main()
