from __future__ import annotations
"""Benchmark classification throughput & (optional) accuracy.

Measures:
  * Throughput (insights/sec) heuristic vs ml vs hybrid
  * Average ms per insight
  * Optional macro F1 if a labeled set is provided (--truth) by reusing classify logic.

Usage:
  python src/cli/benchmark_classify.py --inputs insights_raw.jsonl --modelDir models/tfidf
  python src/cli/benchmark_classify.py --inputs insights_raw.jsonl --modelDir models/tfidf --truth labeled.jsonl --repeats 3

Outputs JSON with per-mode stats and optional quality.
"""
import argparse, json, time, os, sys
from statistics import mean
from pathlib import Path

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from insights.backends import load_backend
from insights.classify import classify as heuristic_classify
from insights.tag_inference import infer_with_validation
from insights.rationale import build_rationale as build_tag_rationale
from insights.metrics import extract_metrics
from insights.adin_taxonomy import TAXONOMY_VERSION

LABELS = ["Advantage","Risk","Neutral"]

def iter_jsonl(path):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def load_truth(path):
    m = {}
    for obj in iter_jsonl(path):
        t = obj.get('text'); l = obj.get('label')
        if t and l in LABELS:
            m[t] = l
    return m

def evaluate(preds, truth_map):
    cm = {a:{b:0 for b in LABELS} for a in LABELS}
    for p in preds:
        t = truth_map.get(p['text'])
        if not t: continue
        cm[t][p['label']] += 1
    eps=1e-9
    per_class = {}
    for lab in LABELS:
        tp = cm[lab][lab]
        fp = sum(cm[o][lab] for o in LABELS if o!=lab)
        fn = sum(cm[lab][o] for o in LABELS if o!=lab)
        prec = tp/(tp+fp+eps); rec = tp/(tp+fn+eps)
        f1 = 2*prec*rec/(prec+rec+eps) if (prec+rec)>0 else 0
        per_class[lab] = {'precision': round(prec,3),'recall': round(rec,3),'f1': round(f1,3)}
    macro_f1 = round(sum(v['f1'] for v in per_class.values())/len(LABELS),3)
    return {'per_class': per_class, 'macro_f1': macro_f1, 'confusion_matrix': cm}

def run_mode(texts, mode, backend=None, risk_th=0.65, adv_th=0.60):
    preds=[]
    start=time.time()
    for t in texts:
        h = heuristic_classify(t)
        tag_inf = infer_with_validation(t)
        final_label = h.label
        probs=None
        if mode in ('ml','hybrid') and backend:
            probs = backend.predict_proba([t])[0]
            if mode=='ml':
                final_label = max(probs.items(), key=lambda kv: kv[1])[0]
            else: # hybrid
                risk_p = probs.get('Risk',0.0)
                adv_p = probs.get('Advantage',0.0)
                if final_label!='Risk' and risk_p>=risk_th:
                    final_label='Risk'
                elif final_label=='Neutral' and adv_p>=adv_th:
                    final_label='Advantage'
        # Precedence with tag inference risk (keep taxonomy consistent)
        if tag_inf.label=='Risk':
            final_label='Risk'
        rationale = build_tag_rationale(final_label, tag_inf.tag, h.signals, [])
        if probs:
            conf = probs.get(final_label,0.0)
        else:
            base={'Risk':0.9,'Advantage':0.7,'Neutral':0.4}[final_label]
            conf=base
        preds.append({'text': t,'label': final_label,'labelTag': tag_inf.tag,'confidence': round(conf,3),'taxonomyVersion': TAXONOMY_VERSION})
    elapsed = time.time()-start
    return preds, {'count': len(preds),'seconds': round(elapsed,3),'insights_per_sec': round(len(preds)/(elapsed+1e-6),2),'avg_ms_per_insight': round((elapsed/len(preds))*1000,3) if preds else None}

def build_parser():
    p=argparse.ArgumentParser(description='Benchmark classification modes.')
    p.add_argument('--inputs', required=True, help='Raw insights JSONL (text field)')
    p.add_argument('--modelDir', help='Model directory for ml/hybrid modes')
    p.add_argument('--truth', help='Optional labeled JSONL for quality metrics')
    p.add_argument('--repeats', type=int, default=1, help='Repeat runs to average timing')
    p.add_argument('--riskThreshold', type=float, default=0.65)
    p.add_argument('--advThreshold', type=float, default=0.60)
    p.add_argument('--out', help='Write benchmark JSON to file')
    return p

def main(argv=None):
    args = build_parser().parse_args(argv)
    texts=[obj.get('text') for obj in iter_jsonl(args.inputs) if obj.get('text')]
    if not texts:
        print('No inputs', file=sys.stderr); sys.exit(1)
    backend=None
    if args.modelDir:
        backend=load_backend(args.modelDir)
    modes=['heuristic'] + (['ml','hybrid'] if backend else [])
    truth_map = load_truth(args.truth) if args.truth else {}
    results={}
    for m in modes:
        stats_runs=[]; preds_all=None
        for _ in range(args.repeats):
            preds, stats = run_mode(texts, m, backend, args.riskThreshold, args.advThreshold)
            stats_runs.append(stats)
            preds_all = preds  # last run (preds deterministic)
        agg = {
            'mode': m,
            'avg_insights_per_sec': round(mean(r['insights_per_sec'] for r in stats_runs),2),
            'avg_ms_per_insight': round(mean(r['avg_ms_per_insight'] for r in stats_runs),3),
            'runs': stats_runs
        }
        if truth_map:
            agg['quality'] = evaluate(preds_all, truth_map)
        results[m] = agg
    out_json = json.dumps({'samples': len(texts), 'modes': results}, indent=2)
    if args.out:
        Path(args.out).write_text(out_json, encoding='utf-8')
    else:
        print(out_json)

if __name__ == '__main__':  # pragma: no cover
    main()
