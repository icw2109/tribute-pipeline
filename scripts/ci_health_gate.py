"""CI Health Gate

Runs:
 1. pytest -q
 2. If tests pass, runs health check on a provided predictions JSONL.

Exit codes:
 0 success (tests pass, health status 0 or allowed)
 1 test failures
 2 health failures (if --strict) else 0 with warning

Usage:
  python scripts/ci_health_gate.py --pred out/insights_classified.jsonl --strict

Additional options pass through to check_health (neutral bounds, min support, entropy, k).
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path

def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, text=True, capture_output=True)

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--pred', required=True, help='Path to predictions JSONL to health-check')
    ap.add_argument('--neutral-min', type=float, default=0.2)
    ap.add_argument('--neutral-max', type=float, default=0.55)
    ap.add_argument('--min-support', type=float, default=0.10)
    ap.add_argument('--entropy-max', type=float, default=1.3)
    ap.add_argument('--k', type=int, default=8)
    ap.add_argument('--strict', action='store_true')
    ap.add_argument('--json', help='Write combined gate result JSON to this file')
    args = ap.parse_args(argv)

    results = {}
    # 1. Tests
    test_proc = run([sys.executable, '-m', 'pytest', '-q'])
    results['pytest'] = {
        'returncode': test_proc.returncode,
        'stdout_tail': '\n'.join(test_proc.stdout.splitlines()[-20:]),
        'failed': test_proc.returncode != 0
    }
    if test_proc.returncode != 0:
        results['status'] = 'tests_failed'
        if args.json:
            Path(args.json).write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(results, indent=2))
        sys.exit(1)

    # 2. Health check
    health_cmd = [sys.executable, 'scripts/check_health.py', '--pred', args.pred, '--neutral-min', str(args.neutral_min), '--neutral-max', str(args.neutral_max), '--min-support', str(args.min_support), '--entropy-max', str(args.entropy_max), '--k', str(args.k)]
    if args.strict:
        health_cmd.append('--strict')
    health_proc = run(health_cmd)
    health_stdout = health_proc.stdout.strip()
    try:
        health_json = json.loads(health_stdout) if health_stdout else {'error':'no_output'}
    except json.JSONDecodeError:
        health_json = {'error':'invalid_json','raw':health_stdout}
    results['health'] = health_json
    fail = False
    if args.strict and health_json.get('status',0) != 0:
        fail = True
    results['status'] = 'ok' if not fail else 'health_failed'
    if args.json:
        Path(args.json).write_text(json.dumps(results, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))
    sys.exit(2 if fail else 0)

if __name__ == '__main__':  # pragma: no cover
    main()
