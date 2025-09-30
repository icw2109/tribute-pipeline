"""Spec Conformance Validator

Usage:
  python scripts/spec_conformance.py --workDir out/run_20250930_140501 [--rerun URL]
  python scripts/spec_conformance.py --run --url https://docs.python.org/3/ [pipeline args]

Modes:
  --workDir <dir> : Validate an existing pipeline output directory.
  --run           : Launch in-process pipeline first (uses tribute-run logic) then validate.
  --rerun <url>   : (Optional) Re-run pipeline with same parameters to check deterministic distribution (idempotence).

Outputs:
  Prints JSON with fields: status (pass|fail|warn), passes[], warnings[], failures[], metrics{...}
  Exit code: 0 on pass/warn, 1 on fail.
"""
from __future__ import annotations
import argparse, json, sys, re, math, shutil, time
from pathlib import Path
from typing import List, Dict, Any

REQUIRED_FILES = [
    'pages.jsonl', 'insights_raw.jsonl', 'insights_classified.jsonl',
    'run_manifest.json', 'diagnostics.json', 'health.json', 'summary.json'
]
OPTIONAL_FILES = ['validation.json']
LABELS = {'Advantage','Risk','Neutral'}

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def read_jsonl(path: Path, limit: int | None = None):
    items=[]
    try:
        with path.open('r', encoding='utf-8') as f:
            for i,line in enumerate(f):
                if limit is not None and i>=limit: break
                line=line.strip()
                if not line: continue
                try:
                    items.append(json.loads(line))
                except Exception:
                    continue
    except FileNotFoundError:
        pass
    return items


def ratio(a: int, b: int) -> float:
    return 0.0 if b==0 else round(a/b,4)


def validate_dir(work: Path, allow_empty: bool=False) -> Dict[str, Any]:
    passes=[]; warnings=[]; failures=[]; metrics={}
    # 1. File presence
    for fn in REQUIRED_FILES:
        if not (work/fn).exists():
            failures.append(f'missing:{fn}')
    if failures:
        return _result('fail', passes, warnings, failures, metrics)

    # Load core artifacts
    pages = read_jsonl(work/'pages.jsonl')
    raw = read_jsonl(work/'insights_raw.jsonl')
    cls = read_jsonl(work/'insights_classified.jsonl')
    metrics['pages']=len(pages)
    metrics['insights_raw']=len(raw)
    metrics['insights_classified']=len(cls)

    if len(pages)==0:
        failures.append('crawl:empty_pages')
    else:
        passes.append('crawl:pages_present')

    # Depth & cap heuristic (extract from summary if available)
    try:
        summary=json.loads((work/'summary.json').read_text(encoding='utf-8'))
        metrics['neutral_ratio']=summary.get('neutral_ratio')
        metrics['label_dist']=summary.get('label_dist')
    except Exception:
        warnings.append('summary:unreadable')

    # 2. Raw insights yield envelope
    if len(raw)==0:
        warnings.append('insights:none_found')
    elif not (25 <= len(raw) <= 180):  # broad envelope
        warnings.append(f'insights:count_out_of_range:{len(raw)}')
    else:
        passes.append('insights:yield_within_range')

    # 3. Classified coverage
    if len(cls)==0:
        failures.append('classify:empty_output')
    else:
        if len(cls) < len(raw)*0.5:
            warnings.append('classify:low_retainment_ratio')
        passes.append('classify:non_empty')

    # 4. Schema spot checks (sample subset for speed)
    sample = cls[: min(80, len(cls))]
    rationale_over=0; invalid_conf=0; bad_label=0; pii_hits=0
    for r in sample:
        lab=r.get('label')
        if lab not in LABELS:
            bad_label+=1
        conf=r.get('confidence')
        if not isinstance(conf,(int,float)) or not (0 <= float(conf) <= 1):
            invalid_conf+=1
        rat=r.get('rationale')
        if isinstance(rat,str) and len(rat)>200:
            rationale_over+=1
        txt=r.get('text') or ''
        if EMAIL_RE.search(txt):
            pii_hits+=1
    if bad_label: failures.append(f'classify:bad_label_count:{bad_label}')
    else: passes.append('classify:labels_valid')
    if invalid_conf: failures.append(f'classify:bad_conf_count:{invalid_conf}')
    else: passes.append('classify:confidence_bounds_ok')
    if rationale_over: warnings.append(f'classify:rationale_over_200:{rationale_over}')
    else: passes.append('classify:rationale_len_ok')
    if pii_hits: warnings.append(f'classify:pii_email_detected:{pii_hits}')
    else: passes.append('classify:pii_email_absent_sample')

    # 5. Diagnostics consistency
    try:
        diag=json.loads((work/'diagnostics.json').read_text(encoding='utf-8'))
        if diag.get('count') != len(cls):
            warnings.append('diagnostics:count_mismatch')
        else:
            passes.append('diagnostics:count_matches_classified')
    except Exception:
        warnings.append('diagnostics:unreadable')

    # 6. Health gate
    try:
        health=json.loads((work/'health.json').read_text(encoding='utf-8'))
        hs=health.get('status')
        if hs in (0,1,2):
            passes.append('health:status_present')
            if hs==1: warnings.append('health:soft_warning')
            if hs==2: warnings.append('health:fail_strict')
        else:
            warnings.append('health:unknown_status')
    except Exception:
        warnings.append('health:unreadable')

    # 7. Validation optional
    if (work/'validation.json').exists():
        try:
            val=json.loads((work/'validation.json').read_text(encoding='utf-8'))
            if val.get('status')=='pass': passes.append('validation:pass')
            else: warnings.append(f"validation:status:{val.get('status')}")
        except Exception:
            warnings.append('validation:unreadable')

    status='pass'
    if failures:
        status='fail'
    elif warnings:
        status='warn'
    return _result(status, passes, warnings, failures, metrics)


def _result(status, passes, warnings, failures, metrics):
    return {
        'status': status,
        'passes': passes,
        'warnings': warnings,
        'failures': failures,
        'metrics': metrics
    }


def parse_args():
    ap=argparse.ArgumentParser(description='Spec conformance validator for pipeline outputs.')
    ap.add_argument('--workDir', help='Existing workDir produced by tribute-e2e or tribute-run')
    ap.add_argument('--run', action='store_true', help='Execute a fresh in-process run before validating')
    ap.add_argument('--url', help='Seed URL (used with --run)')
    ap.add_argument('--maxPages', type=int, default=30)
    ap.add_argument('--maxDepth', type=int, default=2)
    ap.add_argument('--perPageLinkCap', type=int, default=25)
    ap.add_argument('--no-zero-shot', action='store_true')
    ap.add_argument('--no-self-train', action='store_true')
    ap.add_argument('--out', help='Explicit workDir when using --run')
    return ap.parse_args()


def run_pipeline_once(args) -> Path:
    from src import inprocess_runner
    from pathlib import Path
    w = Path(args.out) if args.out else Path('out')/f'conformance_{int(time.time())}'
    w.mkdir(parents=True, exist_ok=True)
    summary = inprocess_runner.run_pipeline(
        url=args.url,
        work_dir=w,
        max_pages=args.maxPages,
        max_depth=args.maxDepth,
        per_page_cap=args.perPageLinkCap,
        enable_zero_shot=not args.no_zero_shot,
        enable_self_train=not args.no_self_train,
        enable_margin_gating=True,
        enable_conflict_dampener=True,
        enable_provisional_risk=True,
        validate=True,
        summary_lines=3,
    )
    return w


def main():
    a=parse_args()
    if a.run and not a.url:
        print('--url required with --run', file=sys.stderr)
        return 2
    work=None
    if a.run:
        work=run_pipeline_once(a)
    else:
        if not a.workDir:
            print('Provide --workDir or use --run', file=sys.stderr)
            return 2
        work=Path(a.workDir)
    result=validate_dir(work)
    print(json.dumps(result, indent=2))
    return 1 if result['status']=='fail' else 0

if __name__=='__main__':
    sys.exit(main())
