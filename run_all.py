"""Single-command convenience runner. (Deprecated)

DEPRECATION NOTICE:
    This script is superseded by:
        python scripts/run_pipeline.py --url <seed> --all
    which now bundles auto workdir creation, feature flags, validation,
    and a human + JSON summary. This file remains for backward
    compatibility and will be removed in a future cleanup pass.

Provides a simpler interface than scripts/run_pipeline.py by:
  * Auto-creating a timestamped work directory under ./out (unless --workDir provided)
  * Enabling commonly desired classifier features by default (zero-shot, self-train, margin gating, conflict dampener, provisional risk)
  * Running validation afterwards
  * Printing a concise human summary plus writing summary.json

Usage (legacy):
    python run_all.py --url https://example.com --maxPages 60
Preferred new usage:
    python scripts/run_pipeline.py --url https://example.com --all

Outputs: workDir/summary.json plus the standard pipeline artifacts.
Exit code: non-zero if pipeline or validation fails (strict health failures propagate).
"""
from __future__ import annotations
import argparse, json, subprocess, sys, datetime, warnings
try:
    from scripts.deprecation import emit_deprecation
except Exception:  # pragma: no cover - fallback if helper missing
    def emit_deprecation(thing, replacement, removal_version):  # type: ignore
        warnings.warn(f"{thing} is deprecated; use {replacement}; removal in {removal_version}", DeprecationWarning, stacklevel=2)
from pathlib import Path

PY = sys.executable
ROOT = Path(__file__).parent
SCRIPTS = ROOT / 'scripts'


def run(cmd: list[str], desc: str, allow_nonzero=False):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0 and not allow_nonzero:
        sys.stderr.write(f"[{desc}] FAILED ({proc.returncode})\nCMD: {' '.join(cmd)}\nSTDERR:\n{proc.stderr}\n")
        raise SystemExit(proc.returncode or 1)
    return proc


def build_parser():
    p = argparse.ArgumentParser(description='Easy end-to-end pipeline runner')
    p.add_argument('--url', required=True, help='Seed URL to crawl')
    p.add_argument('--workDir', help='Explicit work directory (default: out/run_<timestamp>)')
    p.add_argument('--maxPages', type=int, default=40)
    p.add_argument('--maxDepth', type=int, default=2)
    p.add_argument('--rps', type=float, default=1.0)
    p.add_argument('--perPageLinkCap', type=int, default=25)
    p.add_argument('--no-zero-shot', action='store_true', help='Disable zero-shot model')
    p.add_argument('--no-self-train', action='store_true')
    p.add_argument('--no-margin-gating', action='store_true')
    p.add_argument('--no-conflict-dampener', action='store_true')
    p.add_argument('--no-provisional-risk', action='store_true')
    p.add_argument('--strict-health', action='store_true', help='Fail build if health status != 0')
    p.add_argument('--summary-lines', type=int, default=3, help='Number of classified sample lines to include in summary')
    return p


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)

    # Runtime deprecation warning (standardized)
    emit_deprecation('run_all.py', 'python scripts/run_pipeline.py --url <seed> --all', '0.3.0')

    if a.workDir:
        work = Path(a.workDir)
    else:
        ts = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        work = ROOT / 'out' / f'run_{ts}'
    work.mkdir(parents=True, exist_ok=True)

    # Build run_pipeline command
    pipeline_cmd = [PY, str(SCRIPTS / 'run_pipeline.py'), '--url', a.url, '--workDir', str(work), '--maxPages', str(a.maxPages), '--maxDepth', str(a.maxDepth), '--rps', str(a.rps), '--perPageLinkCap', str(a.perPageLinkCap)]
    if not a.no_zero_shot: pipeline_cmd.append('--enable-zero-shot')
    if not a.no_self_train: pipeline_cmd.append('--enable-self-train')
    if not a.no_margin_gating: pipeline_cmd.append('--enable-margin-gating')
    if not a.no_conflict_dampener: pipeline_cmd.append('--enable-conflict-dampener')
    if not a.no_provisional_risk: pipeline_cmd.append('--enable-provisional-risk')
    if a.strict_health: pipeline_cmd.append('--strict')

    proc = run(pipeline_cmd, 'pipeline', allow_nonzero=False)
    try:
        pipeline_summary = json.loads(proc.stdout.splitlines()[-1])
    except Exception:
        pipeline_summary = {}

    classified_path = work / 'insights_classified.jsonl'

    # Validation
    validation_cmd = [PY, str(SCRIPTS / 'validate_delivery.py'), '--workDir', str(work), '--check-rationale-len', '200', '--strict']
    val_proc = run(validation_cmd, 'validation', allow_nonzero=True)
    validation_pass = (val_proc.returncode == 0)
    try:
        validation_json = json.loads(val_proc.stdout)
    except Exception:
        validation_json = {'status': 'unknown'}

    # Sample lines
    samples=[]
    if classified_path.exists():
        with classified_path.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= a.summary_lines: break
                try:
                    rec=json.loads(line)
                    samples.append({'label': rec.get('label'), 'confidence': rec.get('confidence'), 'text': rec.get('text')[:160]})
                except Exception:
                    continue

    # Derive label distribution from diagnostics if present
    diagnostics_path = work / 'diagnostics.json'
    diag = {}
    if diagnostics_path.exists():
        try:
            diag = json.loads(diagnostics_path.read_text(encoding='utf-8'))
        except Exception:
            pass
    label_dist = diag.get('label_dist') or {}
    neutral_ratio = diag.get('neutral_ratio')

    # Health
    health_path = work / 'health.json'
    health_status = None
    if health_path.exists():
        try:
            health_status = json.loads(health_path.read_text(encoding='utf-8')).get('status')
        except Exception:
            health_status = None

    summary = {
        'url': a.url,
        'workDir': str(work),
        'records': diag.get('count'),
        'label_dist': label_dist,
        'neutral_ratio': neutral_ratio,
        'health_status': health_status,
        'validation_status': validation_json.get('status'),
        'samples': samples,
        'pipeline': pipeline_summary,
        'command': ' '.join(pipeline_cmd)
    }

    # Human-readable output
    print("\n=== Pipeline Summary ===")
    print(f"URL: {a.url}")
    print(f"Output: {work}")
    if summary['records'] is not None:
        dist_str = ' '.join(f"{k}:{v}" for k,v in label_dist.items())
        print(f"Records: {summary['records']}  ({dist_str})")
    print(f"Health status: {health_status}")
    print(f"Validation: {summary['validation_status']}")
    for s in samples:
        print(f"  [{s['label']}] ({s['confidence']}) {s['text']}")
    print("========================\n")

    (work / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')

    if not validation_pass:
        raise SystemExit(3)


if __name__ == '__main__':  # pragma: no cover
    main()
