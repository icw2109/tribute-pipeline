#!/usr/bin/env python
"""Smoke test for unified classifier pipeline.

Runs three modes (if resources available):
 1. Heuristic only
 2. Self-train (if model dir provided)
 3. Zero-shot (if transformers installed) optional

Usage:
  python scripts/smoke_test_unified.py --input data/sample.insights.jsonl \
      --model models/selftrain_embed --zero-shot

Creates outputs in out/smoke_*.jsonl and prints a brief summary.
"""
import argparse, json, subprocess, sys, tempfile, statistics, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from insights.classifier_pipeline import PipelineConfig, ClassifierPipeline  # type: ignore


def iter_jsonl(path):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def run_mode(name, cfg: PipelineConfig, input_path: Path, model_dir: str | None, out_path: Path):
    pipe = ClassifierPipeline(cfg, self_train_model_path=model_dir)
    records = []
    with open(out_path,'w',encoding='utf-8') as w:
        for rec in iter_jsonl(input_path):
            txt = rec.get('text')
            if not txt: continue
            out = pipe.classify_text(txt)
            w.write(json.dumps(out, ensure_ascii=False)+'\n')
            records.append(out)
    return records


def summarize(records, name):
    if not records:
        return {'mode': name, 'count': 0}
    labels = [r['label'] for r in records]
    confs = [r['confidence'] for r in records]
    from collections import Counter
    return {
        'mode': name,
        'count': len(records),
        'labelDist': Counter(labels),
        'confidenceMean': round(statistics.mean(confs),3),
        'confidenceMin': min(confs),
        'confidenceMax': max(confs),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--input', required=True, help='Input enriched insights JSONL')
    ap.add_argument('--model', help='Self-train model directory (optional)')
    ap.add_argument('--zero-shot', action='store_true', help='Include zero-shot run')
    ap.add_argument('--limit', type=int, default=25, help='Limit number of insights for speed')
    ap.add_argument('--outdir', default='out', help='Output directory root')
    args = ap.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        print(f'Input file not found: {inp}', file=sys.stderr)
        sys.exit(1)

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    # Prepare a truncated temp file if limiting
    work_input = inp
    if args.limit:
        tmp = outdir / 'smoke_subset.jsonl'
        with open(tmp,'w',encoding='utf-8') as w:
            for i, rec in enumerate(iter_jsonl(inp)):
                if i >= args.limit: break
                w.write(json.dumps({'text': rec.get('text')}, ensure_ascii=False)+'\n')
        work_input = tmp

    summaries = []

    # 1. Heuristic only
    heur_cfg = PipelineConfig(enable_self_train=False, enable_zero_shot=False)
    heur_out = outdir / 'smoke_heuristic.jsonl'
    heur_records = run_mode('heuristic', heur_cfg, work_input, None, heur_out)
    summaries.append(summarize(heur_records, 'heuristic'))

    # 2. Self-train (optional)
    if args.model and Path(args.model).exists():
        st_cfg = PipelineConfig(enable_self_train=True, enable_zero_shot=False)
        st_out = outdir / 'smoke_selftrain.jsonl'
        st_records = run_mode('self_train', st_cfg, work_input, args.model, st_out)
        summaries.append(summarize(st_records, 'self_train'))
    else:
        summaries.append({'mode':'self_train','skipped':'no model dir'})

    # 3. Zero-shot (optional)
    if args.zero_shot:
        try:
            import transformers  # noqa: F401
            zs_cfg = PipelineConfig(enable_self_train=False, enable_zero_shot=True)
            zs_out = outdir / 'smoke_zeroshot.jsonl'
            zs_records = run_mode('zero_shot', zs_cfg, work_input, None, zs_out)
            summaries.append(summarize(zs_records, 'zero_shot'))
        except Exception as e:
            summaries.append({'mode':'zero_shot','skipped': f'transformers not available: {e}'})

    print(json.dumps({'summaries': summaries, 'outDir': str(outdir)}, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
