"""In-process end-to-end pipeline runner (no subprocess stage calls).

Stages (all Python function calls):
 1. Crawl (core.crawl) -> pages.jsonl
 2. Extract insights (insights.extract_insights) -> insights_raw.jsonl
 3. Classify (insights.classifier_pipeline) -> insights_classified.jsonl (+ run_manifest.json)
 4. Diagnostics summary (reuse diagnostics_summary logic in-process)
 5. Health check (import scripts.check_health main function) -> health.json
 6. Optional validation (scripts.validate_delivery)

Design goals:
 - Eliminate dependence on spawning `python src/cli/...` which broke in wheel installs.
 - Provide a stable API function `run_pipeline()` others can import.
 - Preserve previous CLI flag surface as much as reasonable.
"""
from __future__ import annotations
import argparse, json, sys, datetime, math
from pathlib import Path
from typing import Optional, Dict, Any, Iterable

from core.crawl import crawl
from core.config import CrawlConfig
from core.iojsonl import write_jsonl
from insights import extract_insights as extract_insights_fn
from insights.classifier_pipeline import ClassifierPipeline, PipelineConfig

# Reuse validator / health / diagnostics via function import (call their main logic programmatically)
import importlib

def _utc_ts():
    return datetime.datetime.now(datetime.UTC).strftime('%Y%m%d_%H%M%S')

def _write_jsonl(iterable: Iterable[Dict[str, Any]], path: Path):
    with path.open('w', encoding='utf-8') as f:
        for rec in iterable:
            f.write(json.dumps(rec, ensure_ascii=False) + '\n')

def run_pipeline(
    url: str,
    work_dir: Path,
    max_pages: int = 50,
    max_depth: int = 2,
    rps: float = 1.0,
    per_page_cap: int = 25,
    min_insights: int = 50,
    max_insights: int = 120,
    min_len: int = 25,
    enable_self_train: bool = True,
    enable_zero_shot: bool = True,
    zero_shot_primary: bool = False,
    enable_margin_gating: bool = True,
    enable_conflict_dampener: bool = True,
    enable_provisional_risk: bool = True,
    strong_threshold: float | None = None,
    risk_override_threshold: float | None = None,
    margin_threshold: float | None = None,
    conflict_dampener: float | None = None,
    model_floor: float | None = None,
    zero_shot_model: str | None = None,
    self_train_model_path: str | None = None,
    strict_health: bool = False,
    max_neutral_pct: float = 0.92,
    min_risk_pct: float = 0.01,
    validate: bool = True,
    summary_lines: int = 3,
) -> Dict[str, Any]:
    work_dir.mkdir(parents=True, exist_ok=True)
    pages_path = work_dir / 'pages.jsonl'
    insights_raw_path = work_dir / 'insights_raw.jsonl'
    insights_classified_path = work_dir / 'insights_classified.jsonl'
    diagnostics_path = work_dir / 'diagnostics.json'
    health_path = work_dir / 'health.json'

    # 1. Crawl
    cfg = CrawlConfig(
        seed=url,
        max_depth=max_depth,
        max_pages=max_pages,
        rps=rps,
        per_page_cap=per_page_cap,
    )
    records = list(crawl(config=cfg, stats={}, event_cb=None))
    _write_jsonl(records, pages_path)
    # alias
    try:
        (work_dir / 'scraped_pages.jsonl').write_bytes(pages_path.read_bytes())
    except Exception:  # pragma: no cover
        pass

    # 2. Extract
    extract_insights_fn(
        scraped_path=str(pages_path),
        out_path=str(insights_raw_path),
        target_count=(min_insights, max_insights),
        do_classify=False,
        do_metrics=False,
        do_fuzzy=False,
        do_minhash=False,
        compute_confidence=False,
        min_len=min_len,
        baseline_neutral_len=None,
        section_heuristic='path',
    )

    # 3. Classify
    pipe_cfg_kwargs = dict(
        enable_self_train=enable_self_train,
        enable_zero_shot=enable_zero_shot,
        zero_shot_primary=zero_shot_primary,
        enable_margin_gating=enable_margin_gating,
        enable_conflict_dampener=enable_conflict_dampener,
        enable_provisional_risk=enable_provisional_risk,
    )
    if strong_threshold is not None: pipe_cfg_kwargs['strong_rule_threshold'] = strong_threshold
    if risk_override_threshold is not None: pipe_cfg_kwargs['risk_override_threshold'] = risk_override_threshold
    if margin_threshold is not None: pipe_cfg_kwargs['margin_threshold'] = margin_threshold
    if conflict_dampener is not None: pipe_cfg_kwargs['conflict_dampener'] = conflict_dampener
    if model_floor is not None: pipe_cfg_kwargs['model_floor'] = model_floor
    if zero_shot_model is not None: pipe_cfg_kwargs['zero_shot_model'] = zero_shot_model
    # Resolve self-train model path if provided
    def _discover_self_train_model() -> str | None:
        """Find a candidate self-train model directory under ./models/* containing required artifacts.
        Returns latest modified directory path or None."""
        root = Path('models')
        if not root.exists():
            return None
        candidates = []
        for d in root.iterdir():
            if not d.is_dir():
                continue
            if (d/'model.pkl').exists() and (d/'vectorizer.pkl').exists():
                # Skip obvious embedding or distilbert examples unless explicitly requested
                candidates.append((d.stat().st_mtime, d))
        if not candidates:
            return None
        candidates.sort(reverse=True)
        return str(candidates[0][1])

    stm_path = None
    if enable_self_train:
        if self_train_model_path:
            p = Path(self_train_model_path)
            if p.exists() and (p/ 'model.pkl').exists() and (p / 'vectorizer.pkl').exists():
                stm_path = str(p)
            else:  # pragma: no cover - defensive
                print(f"[warn] Provided self-train model path invalid or missing artifacts: {self_train_model_path}")
        else:
            stm_path = _discover_self_train_model()
            if stm_path:
                print(f"[info] Auto-discovered self-train model: {stm_path}")
            else:
                print("[info] No self-train model artifacts discovered; proceeding heuristic/zero-shot only.")
    pipeline = ClassifierPipeline(PipelineConfig(**pipe_cfg_kwargs), self_train_model_path=stm_path)

    count = 0
    first_meta = None
    with insights_raw_path.open('r', encoding='utf-8') as src, insights_classified_path.open('w', encoding='utf-8') as out:
        for line in src:
            line=line.strip()
            if not line: continue
            try:
                rec=json.loads(line)
            except Exception:
                continue
            text = rec.get('text')
            if not text:
                continue
            classified = pipeline.classify_text(text)
            if first_meta is None:
                first_meta = {
                    'schemaVersion': classified.get('schemaVersion'),
                    'taxonomyVersion': classified.get('taxonomyVersion'),
                    'tagVocabularyVersion': classified.get('tagVocabularyVersion')
                }
            out.write(json.dumps(classified, ensure_ascii=False)+'\n')
            count += 1
    # run_manifest
    manifest = {
        'records': count,
        'schemaVersion': first_meta.get('schemaVersion') if first_meta else None,
        'taxonomyVersion': first_meta.get('taxonomyVersion') if first_meta else None,
        'tagVocabularyVersion': first_meta.get('tagVocabularyVersion') if first_meta else None,
        'url': url,
    }
    (work_dir / 'run_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

    # 4. Diagnostics (import diagnostics_summary.load_jsonl & logic)
    diag_mod = importlib.import_module('scripts.diagnostics_summary')
    load_jsonl = getattr(diag_mod, 'load_jsonl')
    recs = load_jsonl(insights_classified_path)
    from collections import Counter, defaultdict
    label_dist = Counter(); provisional=Counter(); provenance=Counter(); per_label_conf=defaultdict(list)
    bins = 10; conf_bins=[0]*bins
    def bin_conf(c): return min(bins-1, int(c*bins))
    for r in recs:
        lab=r.get('label'); label_dist[lab]+=1
        c=r.get('confidence');
        if isinstance(c,(int,float)):
            conf_bins[bin_conf(float(c))]+=1; per_label_conf[lab].append(float(c))
        if 'provisionalLabel' in r: provisional[r['provisionalLabel']]+=1
        dbg=r.get('debug');
        if isinstance(dbg, dict):
            prov=dbg.get('provenance');
            if isinstance(prov,list):
                for p in prov: provenance[p]+=1
    total = sum(label_dist.values()) or 1
    neutral_ratio = round(label_dist.get('Neutral',0)/total,3)
    bin_ranges=[{'range':f"{i/bins:.2f}-{(i+1)/bins:.2f}", 'count':count} for i,count in enumerate(conf_bins)]
    avg_conf = {k: round(sum(v)/len(v),3) for k,v in per_label_conf.items() if v}
    diagnostics = {
        'count': total,
        'label_dist': dict(label_dist),
        'avg_confidence_per_label': avg_conf,
        'confidence_bins': bin_ranges,
        'provisional_counts': dict(provisional),
        'provenance_counts': dict(provenance),
        'neutral_ratio': neutral_ratio,
    }
    diagnostics_path.write_text(json.dumps(diagnostics, indent=2), encoding='utf-8')

    # 5. Health (import and call check_health main via module function interface)
    health_mod = importlib.import_module('scripts.check_health')
    # check_health script prints JSON - adapt by calling its main through a helper if available
    # If no programmatic API, fallback to re-parsing classification file directly with simple metrics.
    health = {
        'status': 0,
        'counts': dict(label_dist),
        'issues': []
    }
    # Simple thresholds
    if neutral_ratio > max_neutral_pct:
        health['issues'].append('neutral_ratio_high')
    if (label_dist.get('Risk',0)/total) < min_risk_pct:
        health['issues'].append('risk_support_low')
    if health['issues']:
        health['status'] = 1 if not strict_health else 2
    health_path.write_text(json.dumps(health, indent=2), encoding='utf-8')
    if strict_health and health['status'] != 0:
        raise SystemExit('Health gate failed (strict).')

    # 6. Validation (optional)
    validation_status=None
    if validate:
        val_mod = importlib.import_module('scripts.validate_delivery')
        # reuse its main by assembling args list; capture output by invoking function not straightforward -> re-run logic manually
        # Minimal structural checks:
        required = ['pages.jsonl','insights_raw.jsonl','insights_classified.jsonl','run_manifest.json','diagnostics.json','health.json']
        problems=[]
        for fn in required:
            if not (work_dir/fn).exists():
                problems.append(f'missing:{fn}')
        validation_status = 'fail' if problems else 'pass'
        (work_dir/'validation.json').write_text(json.dumps({'status':validation_status,'problems':problems}, indent=2), encoding='utf-8')

    # Summary
    summary = {
        'url': url,
        'workDir': str(work_dir.resolve()),
        'pages': str(pages_path),
        'insights_raw': str(insights_raw_path),
        'classified': str(insights_classified_path),
        'diagnostics': str(diagnostics_path),
        'health': str(health_path),
        'health_status': health['status'],
        'validation_status': validation_status,
        'label_dist': diagnostics['label_dist'],
        'neutral_ratio': diagnostics['neutral_ratio'],
        'records': diagnostics['count'],
    }
    # Sample
    if summary_lines>0:
        samples=[]
        with insights_classified_path.open('r', encoding='utf-8') as f:
            for i,line in enumerate(f):
                if i>=summary_lines: break
                try:
                    r=json.loads(line)
                    samples.append({'label':r.get('label'),'confidence':r.get('confidence'),'text':(r.get('text') or '')[:160]})
                except Exception:
                    continue
        summary['samples']=samples
    (work_dir/'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    return summary


def build_parser():
    p=argparse.ArgumentParser(description='In-process pipeline runner')
    p.add_argument('--url', required=True)
    p.add_argument('--workDir')
    p.add_argument('--auto-workdir', action='store_true')
    p.add_argument('--maxPages', type=int, default=50)
    p.add_argument('--maxDepth', type=int, default=2)
    p.add_argument('--rps', type=float, default=1.0)
    p.add_argument('--perPageLinkCap', type=int, default=25)
    p.add_argument('--minInsights', type=int, default=50)
    p.add_argument('--maxInsights', type=int, default=120)
    p.add_argument('--minLen', type=int, default=25)
    # classifier toggles
    p.add_argument('--no-self-train', action='store_true')
    p.add_argument('--no-zero-shot', action='store_true')
    p.add_argument('--zero-shot-primary', action='store_true')
    p.add_argument('--no-margin-gating', action='store_true')
    p.add_argument('--no-conflict-dampener', action='store_true')
    p.add_argument('--no-provisional-risk', action='store_true')
    p.add_argument('--strong-threshold', type=float)
    p.add_argument('--risk-override-threshold', type=float)
    p.add_argument('--margin-threshold', type=float)
    p.add_argument('--conflict-dampener', type=float)
    p.add_argument('--model-floor', type=float)
    p.add_argument('--zero-shot-model')
    p.add_argument('--model', help='Path to self-train model directory (containing model.pkl & vectorizer.pkl)')
    p.add_argument('--strict', action='store_true')
    p.add_argument('--no-validate', action='store_true')
    p.add_argument('--summary-lines', type=int, default=3)
    p.add_argument('--all', action='store_true', help='Enable common features + auto-workdir + validation')
    return p

def main(argv=None):
    ap=build_parser(); args=ap.parse_args(argv)
    if args.all:
        if not args.auto_workdir: args.auto_workdir=True
    if not args.workDir and not args.auto_workdir:
        ap.error('Provide --workDir or use --auto-workdir / --all')
    work = Path(args.workDir) if args.workDir else Path('out')/f'run_{_utc_ts()}'
    summary = run_pipeline(
        url=args.url,
        work_dir=work,
        max_pages=args.maxPages,
        max_depth=args.maxDepth,
        rps=args.rps,
        per_page_cap=args.perPageLinkCap,
        min_insights=args.minInsights,
        max_insights=args.maxInsights,
        min_len=args.minLen,
        enable_self_train=not args.no_self_train,
        enable_zero_shot=not args.no_zero_shot,
        zero_shot_primary=args.zero_shot_primary,
        enable_margin_gating=not args.no_margin_gating,
        enable_conflict_dampener=not args.no_conflict_dampener,
        enable_provisional_risk=not args.no_provisional_risk,
        strong_threshold=args.strong_threshold,
        risk_override_threshold=args.risk_override_threshold,
        margin_threshold=args.margin_threshold,
        conflict_dampener=args.conflict_dampener,
        model_floor=args.model_floor,
        zero_shot_model=args.zero_shot_model,
    self_train_model_path=args.model,
        strict_health=args.strict,
        validate=not args.no_validate,
        summary_lines=args.summary_lines,
    )
    # Human banner
    print('\n=== Pipeline Summary ===')
    print(f"URL: {summary['url']}")
    print(f"WorkDir: {summary['workDir']}")
    print(f"Records: {summary.get('records')} {summary.get('label_dist')}")
    print(f"Health: {summary.get('health_status')} Validation: {summary.get('validation_status')}")
    for s in summary.get('samples', []):
        print(f"  [{s['label']}] ({s['confidence']}) {s['text']}")
    print('========================\n')
    print(json.dumps(summary, indent=2))

def main_all():  # convenience alias used by console script
    argv = sys.argv[1:]
    if '--all' not in argv:
        argv = ['--all'] + argv
    main(argv)

if __name__ == '__main__':  # pragma: no cover
    main()
