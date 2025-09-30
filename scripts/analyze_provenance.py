"""Analyze classifier provenance usage (heuristic, self-train, zero-shot) on real pipeline output.

Usage:
    python scripts/analyze_provenance.py --workDir out/run_YYYYMMDD_HHMMSS [--sample 250] [--reclassify]

Modes:
    * Default: If insights_classified.jsonl has debug.provenance fields, aggregate directly.
    * --reclassify: Reclassify insights_raw.jsonl with a debug-enabled pipeline (fast) to derive provenance even if
        production run omitted debug info. Writes insights_classified_debug.jsonl (optional reuse with --debugOut).

Outputs JSON summary (stdout):
    {
        "total": N,
        "provenance_counts": {...},
        "provenance_pct": {...},
        "label_by_provenance": {prov:{label:count}},
        "recommendations": [ ... ]
    }
Exit code 0 always (pure analysis).
"""
from __future__ import annotations
import argparse, json, random, sys
from pathlib import Path
from collections import Counter, defaultdict

# Robust import: allow running without editable install by injecting 'src' onto sys.path if needed.
try:  # pragma: no cover - simple defensive shim
    from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig
except ModuleNotFoundError:  # attempt local source tree resolution
    repo_root = Path(__file__).resolve().parents[1]
    candidate = repo_root / 'src'
    if candidate.exists():
        sys.path.insert(0, str(candidate))
        try:
            from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig  # type: ignore
        except ModuleNotFoundError as e:  # re-raise with context
            raise ModuleNotFoundError(
                "Could not import 'insights'. Ensure you ran 'pip install -e .' or that 'src' exists."
            ) from e
    else:
        raise
PROV_KEYS_INTEREST = [
        'heuristic-only','self-train','self-train-refine','zero-shot-fallback',
        'zero-shot-primary','risk-override','provisional-risk','provisional-advantage','nli-margin-lock'
]

def parse_args():
    ap=argparse.ArgumentParser(description='Provenance usage analysis for classifier pipeline.')
    ap.add_argument('--workDir', required=True)
    ap.add_argument('--sample', type=int, default=0, help='Limit analysis to a random sample (0 = all)')
    ap.add_argument('--reclassify', action='store_true', help='Reclassify raw insights with debug=True to capture provenance')
    ap.add_argument('--debugOut', help='Optional path to write debug classification JSONL when reclassifying')
    ap.add_argument('--no-zero-shot', action='store_true')
    ap.add_argument('--no-self-train', action='store_true')
    ap.add_argument('--model', help='Path to self-train model directory (model.pkl & vectorizer.pkl). Auto-discovery if omitted.')
    return ap.parse_args()


def load_jsonl(path: Path, sample: int = 0):
    lines=[]
    with path.open('r', encoding='utf-8') as f:
        for ln in f:
            ln=ln.strip()
            if not ln: continue
            try:
                lines.append(json.loads(ln))
            except Exception:
                continue
    if sample and len(lines)>sample:
        random.seed(0)
        lines=random.sample(lines, sample)
    return lines


def reclassify(raw_path: Path, cfg) -> list[dict]:
    pipe=ClassifierPipeline(cfg)
    out=[]
    with raw_path.open('r', encoding='utf-8') as f:
        for ln in f:
            ln=ln.strip()
            if not ln: continue
            try:
                rec=json.loads(ln)
            except Exception:
                continue
            txt=rec.get('text')
            if not txt: continue
            out.append(pipe.classify_text(txt))
    return out


def analyze(records: list[dict]):
    prov_counter=Counter(); label_by_prov=defaultdict(Counter)
    missing_debug=0
    for r in records:
        dbg=r.get('debug')
        if not dbg or 'provenance' not in dbg:
            prov=['heuristic-only']
            missing_debug+=1
        else:
            prov=dbg.get('provenance') or []
            if not prov:
                prov=['heuristic-only']
        seen=set()
        for p in prov:
            prov_counter[p]+=1
            seen.add(p)
        # Single primary provenance bucket for label_by_prov (take first)
        primary=prov[0]
        label_by_prov[primary][r.get('label')] += 1
    total=sum(prov_counter.values()) or 1
    prov_pct={k: round(v/total,4) for k,v in prov_counter.items()}

    recs=[]
    # Recommendations heuristics
    if prov_pct.get('zero-shot-fallback',0) < 0.02 and prov_pct.get('zero-shot-primary',0)==0:
        recs.append('Zero-shot rarely triggered (<2%): consider raising model_floor or lowering strong_rule_threshold.')
    if prov_pct.get('self-train',0)+prov_pct.get('self-train-refine',0) < 0.03:
        recs.append('Self-train almost unused (<3%): heuristic rules may be too strong; consider lowering strong_rule_threshold or disabling heuristics for borderline.')
    if prov_pct.get('risk-override',0) > 0.15:
        recs.append('High risk-override frequency (>15%): risk heuristic threshold may be too aggressive.')
    if prov_pct.get('provisional-risk',0) == 0 and prov_pct.get('zero-shot-fallback',0)>0:
        recs.append('No provisional-risk despite fallbacks: consider enabling enable_provisional_risk or lowering risk_override_threshold.')

    return {
        'total': total,
        'provenance_counts': dict(prov_counter),
        'provenance_pct': prov_pct,
        'label_by_provenance': {k: dict(v) for k,v in label_by_prov.items()},
        'missing_debug_backfilled': missing_debug,
        'recommendations': recs
    }


def main():
    args=parse_args()
    work=Path(args.workDir)
    cls_path=work/'insights_classified.jsonl'
    raw_path=work/'insights_raw.jsonl'
    records=[]
    # Load existing classified
    if cls_path.exists():
        records=load_jsonl(cls_path, sample=args.sample)
    needs_reclass=args.reclassify or not any('debug' in r for r in records[:20])
    if needs_reclass:
        # Discover self-train model directory if not provided
        stm_path = None
        if not args.no_self_train:
            if args.model:
                p=Path(args.model)
                if p.exists() and (p/'model.pkl').exists() and (p/'vectorizer.pkl').exists():
                    stm_path=str(p)
                else:
                    print(f"[warn] --model path invalid or missing artifacts: {args.model}")
            else:
                root=Path('models')
                if root.exists():
                    candidates=[]
                    for d in root.iterdir():
                        if d.is_dir() and (d/'model.pkl').exists() and (d/'vectorizer.pkl').exists():
                            candidates.append((d.stat().st_mtime, d))
                    if candidates:
                        candidates.sort(reverse=True)
                        stm_path=str(candidates[0][1])
                        print(f"[info] Auto-discovered self-train model for provenance analysis: {stm_path}")
                if stm_path is None:
                    print('[info] No self-train model found for analysis reclassification.')

        cfg=PipelineConfig(
            enable_self_train=not args.no_self_train,
            enable_zero_shot=not args.no_zero_shot,
            enable_margin_gating=True,
            enable_conflict_dampener=True,
            enable_provisional_risk=True,
            debug=True
        )
        # If sampling for speed, subsample raw first
        raw_records=load_jsonl(raw_path, sample=args.sample)
        records=[]
        from insights.classifier_pipeline import ClassifierPipeline  # local import to honor path injection earlier
        pipe=ClassifierPipeline(cfg, self_train_model_path=stm_path)
        for r in raw_records:
            txt=r.get('text')
            if not txt: continue
            records.append(pipe.classify_text(txt))
        if args.debugOut:
            with open(args.debugOut,'w',encoding='utf-8') as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False)+'\n')
    result=analyze(records)
    print(json.dumps(result, indent=2))
    return 0

if __name__=='__main__':
    sys.exit(main())
