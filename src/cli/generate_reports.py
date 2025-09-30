from __future__ import annotations
"""Generate markdown reports: classification metrics & qualitative examples.

Usage:
  python -m cli.generate_reports --predictions insights_classified.jsonl --truth labeled.jsonl \
      --benchmark benchmark.json --outDir reports/ --costPerSecond 0.0004

Inputs:
  --predictions: JSONL with fields text,label,confidence,labelTag (output of classify)
  --truth: JSONL with ground truth (text,label)
  --benchmark: Optional JSON or JSONL containing latency metrics (ms per insight) per mode.
  --outDir: directory to write classification_metrics.md and examples.md

This is a lightweight utility; for large corpora prefer streaming evaluation.
"""
import argparse, json, os, sys, statistics, math
from pathlib import Path
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

def load_truth(path: str) -> Dict[str,str]:
    m = {}
    for obj in iter_jsonl(path):
        t = obj.get('text'); l = obj.get('label')
        if t and l:
            m[t] = l
    return m

def evaluate(pred_path: str, truth_map: Dict[str,str]):
    preds = list(iter_jsonl(pred_path))
    cm = {a:{b:0 for b in LABELS} for a in LABELS}
    for p in preds:
        t = truth_map.get(p.get('text'))
        pl = p.get('label')
        if t in LABELS and pl in LABELS:
            cm[t][pl]+=1
    metrics = {}
    eps=1e-9
    for lab in LABELS:
        tp = cm[lab][lab]
        fp = sum(cm[o][lab] for o in LABELS if o!=lab)
        fn = sum(cm[lab][o] for o in LABELS if o!=lab)
        prec = tp/(tp+fp+eps); rec = tp/(tp+fn+eps)
        f1 = 2*prec*rec/(prec+rec+eps) if (prec+rec)>0 else 0
        metrics[lab] = {'precision': round(prec,3),'recall': round(rec,3),'f1': round(f1,3)}
    macro_f1 = round(sum(m['f1'] for m in metrics.values())/len(LABELS),3)
    return preds, {'confusion_matrix': cm, 'per_class': metrics, 'macro_f1': macro_f1}

def cost_estimate(latency_ms: float, cost_per_second: float, count: int):
    seconds = (latency_ms/1000.0)*count
    return seconds * cost_per_second

def write_metrics_md(path: Path, evaluation: Dict, benchmark: Dict|None, cost_per_second: float, sample_count: int):
    with path.open('w',encoding='utf-8') as w:
        w.write('# Classification Metrics\n\n')
        w.write(f"Macro F1: **{evaluation['macro_f1']}**\n\n")
        w.write('## Per-Class\n')
        for lab, m in evaluation['per_class'].items():
            w.write(f"- {lab}: P={m['precision']} R={m['recall']} F1={m['f1']}\n")
        w.write('\n## Confusion Matrix\n')
        cm = evaluation['confusion_matrix']
        w.write('|True\\Pred|'+ '|'.join(LABELS)+'|\n')
        w.write('|---|'+'|'.join(['---']*len(LABELS))+'|\n')
        for t in LABELS:
            row = '|'.join(str(cm[t][p]) for p in LABELS)
            w.write(f'|{t}|{row}|\n')
        if benchmark:
            w.write('\n## Latency & Cost Estimates\n')
            w.write('|Mode|Avg ms/insight|Est. cost per 1k insights|\n')
            w.write('|---|---|---|\n')
            for mode, stats in benchmark.items():
                ms = stats.get('avg_ms_per_insight') or stats.get('ms_per_insight') or 0
                cost = cost_estimate(ms, cost_per_second, 1000)
                w.write(f"|{mode}|{round(ms,3)}|${cost:.4f}|\n")
        w.write('\n_This report is auto-generated._\n')

def write_examples(preds: List[Dict], path: Path):
    high = sorted([p for p in preds if p.get('confidence',0)>=0.75], key=lambda x: -x.get('confidence',0))[:10]
    low = sorted([p for p in preds if 0.3 <= p.get('confidence',0) <= 0.55], key=lambda x: x.get('confidence',0))[:10]
    with path.open('w',encoding='utf-8') as w:
        w.write('# Qualitative Examples\n\n')
        if high:
            w.write('## High Confidence Correct (sample)\n')
            for p in high:
                w.write(f"- {p.get('label')} | {p.get('labelTag')} | {p.get('confidence')} :: {p.get('text')}\n")
            w.write('\n')
        if low:
            w.write('## Low / Borderline Confidence (sample)\n')
            for p in low:
                w.write(f"- {p.get('label')} | {p.get('labelTag')} | {p.get('confidence')} :: {p.get('text')}\n")


def parse_benchmark(path: str|None):
    if not path:
        return None
    p = Path(path)
    if not p.exists():
        return None
    # Support JSON or JSONL (keyed objects)
    try:
        txt = p.read_text(encoding='utf-8').strip()
        if not txt:
            return None
        if txt.startswith('{'):
            return json.loads(txt)
        # else treat as JSONL list of records with mode
        out={}
        for obj in iter_jsonl(str(p)):
            mode = obj.get('mode') or obj.get('name')
            if mode:
                out[mode]=obj
        return out
    except Exception:
        return None


def build_parser():
    a = argparse.ArgumentParser(description='Generate markdown metrics & qualitative examples.')
    a.add_argument('--predictions', required=True)
    a.add_argument('--truth', required=True)
    a.add_argument('--benchmark', help='Benchmark JSON/JSONL with latency stats per mode')
    a.add_argument('--outDir', required=True)
    a.add_argument('--costPerSecond', type=float, default=0.0004, help='Estimated compute $ cost per CPU second')
    return a


def main(argv=None):
    args = build_parser().parse_args(argv)
    truth_map = load_truth(args.truth)
    preds, eval_metrics = evaluate(args.predictions, truth_map)
    bench = parse_benchmark(args.benchmark)
    out_dir = Path(args.outDir); out_dir.mkdir(parents=True, exist_ok=True)
    write_metrics_md(out_dir / 'classification_metrics.md', eval_metrics, bench, args.costPerSecond, len(preds))
    write_examples(preds, out_dir / 'examples.md')
    print(json.dumps({'written': str(out_dir), 'macro_f1': eval_metrics['macro_f1']}, indent=2))

if __name__ == '__main__':  # pragma: no cover
    main()
