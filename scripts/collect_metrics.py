"""Unified metrics collector.

Aggregates diagnostics, health, validation, and summary artifacts from one or more
pipeline work directories. Produces a consolidated JSON document suitable for
dashboards or longitudinal tracking.

Example:
    python scripts/collect_metrics.py --workDir out/run_20250930_120301 --out metrics.json
    python scripts/collect_metrics.py --glob 'out/run_*' --aggregate metrics_timeseries.json
"""
from __future__ import annotations
import argparse, json, sys, glob, datetime
from pathlib import Path

def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None

def collect_single(work: Path):
    diagnostics = load_json(work / 'diagnostics.json') or {}
    health = load_json(work / 'health.json') or {}
    validation = load_json(work / 'validation.json') or {}
    summary = load_json(work / 'summary.json') or {}

    # Insight count fallback: prefer summary.insight_count else count lines in insights_raw.jsonl
    insight_count = summary.get('insight_count')
    if insight_count is None:
        ir = work / 'insights_raw.jsonl'
        if ir.exists():
            try:
                with ir.open('r', encoding='utf-8') as f:
                    insight_count = sum(1 for _ in f)
            except Exception:
                insight_count = None

    record = {
        'workDir': str(work),
        'timestamp': datetime.datetime.utcnow().replace(microsecond=0).isoformat() + 'Z',
        'diagnostics': {
            'count': diagnostics.get('count'),
            'label_dist': diagnostics.get('label_dist'),
            'neutral_ratio': diagnostics.get('neutral_ratio'),
            'confidence_bins': diagnostics.get('confidence_bins'),
        },
        'health': {'status': health.get('status'), 'details': {k: v for k, v in health.items() if k != 'status'}},
        'validation': {'status': validation.get('status'), 'details': {k: v for k, v in validation.items() if k != 'status'}},
        'insight_count': insight_count,
    }
    # Attach pipeline summary subset if present
    if summary:
        record['pipeline'] = {
            'url': summary.get('url'),
            'records': summary.get('records'),
            'health_status': summary.get('health_status'),
            'validation_status': summary.get('validation_status'),
        }
    return record

def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Aggregate pipeline metrics into a single JSON structure')
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument('--workDir', help='Single work directory to collect')
    g.add_argument('--glob', dest='pattern', help='Glob pattern for multiple work directories (quote in shell)')
    p.add_argument('--out', help='Output JSON file for single collection (default: stdout)')
    p.add_argument('--aggregate', help='Output JSON file for multi collection (ignored for single)')
    p.add_argument('--min-label-count', type=int, default=0, help='Optional filter: require diagnostics.count >= this')
    return p.parse_args(argv)

def main(argv=None):
    a = parse_args(argv)
    if a.workDir:
        work = Path(a.workDir)
        if not work.exists():
            sys.stderr.write(f"Work directory not found: {work}\n")
            return 2
        record = collect_single(work)
        out_json = json.dumps(record, indent=2)
        if a.out:
            Path(a.out).write_text(out_json, encoding='utf-8')
        else:
            print(out_json)
        return 0
    else:
        paths = [Path(p) for p in glob.glob(a.pattern)]
        paths = [p for p in paths if p.is_dir()]
        records = []
        for p in sorted(paths):
            rec = collect_single(p)
            cnt = (rec.get('diagnostics') or {}).get('count') or 0
            if cnt >= a.min_label_count:
                records.append(rec)
        out_obj = {'runs': records, 'count': len(records)}
        out_json = json.dumps(out_obj, indent=2)
        if a.aggregate:
            Path(a.aggregate).write_text(out_json, encoding='utf-8')
        else:
            print(out_json)
        return 0

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
