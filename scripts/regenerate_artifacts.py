"""Automate regeneration of all primary pipeline artifacts for a given seed URL.

Sequence (default):
 1. Scrape -> pages.jsonl
 2. Extract -> insights_raw.jsonl
 3. Classify -> insights_classified.jsonl (+ run_manifest.json)
 4. Diagnostics -> diagnostics.json
 5. Health check -> health.json
 6. Qualitative examples -> qualitative_examples.md
 7. Evidence/labelTag audit -> audit_evidence_labeltag.json
 8. (Optional) Apply calibration -> insights_classified_calibrated.jsonl

Idempotent: existing output files are overwritten each run.

Exit codes:
 0 success (or health warnings when not --strict)
 1 failed subprocess (scrape/extract/classify/other)
 2 strict health gate failure (status != 0)

Examples:
  python scripts/regenerate_artifacts.py --url https://www.eigenlayer.xyz --outDir out/eigen --enable-zero-shot --strict
  python scripts/regenerate_artifacts.py --url https://example.com --outDir out/example --calibration calibration/temperature.json
"""
from __future__ import annotations
import argparse, json, subprocess, sys
from pathlib import Path


def run(cmd: list[str], desc: str):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"[{desc}] FAILED: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n")
        raise SystemExit(1)
    return proc.stdout.strip()


def build_parser():
    p = argparse.ArgumentParser(description="Regenerate all core artifacts end-to-end")
    p.add_argument('--url', required=True, help='Seed URL to crawl')
    p.add_argument('--outDir', required=True, help='Output directory root')
    p.add_argument('--maxPages', type=int, default=50)
    p.add_argument('--maxDepth', type=int, default=2)
    p.add_argument('--rps', type=float, default=1.0)
    p.add_argument('--perPageLinkCap', type=int, default=25)
    p.add_argument('--minInsights', type=int, default=50)
    p.add_argument('--maxInsights', type=int, default=110)
    p.add_argument('--minLen', type=int, default=25)
    # Classification feature toggles (subset of run_pipeline for simplicity)
    p.add_argument('--enable-zero-shot', action='store_true')
    p.add_argument('--enable-conflict-dampener', action='store_true')
    p.add_argument('--enable-margin-gating', action='store_true')
    p.add_argument('--enable-provisional-risk', action='store_true')
    p.add_argument('--enable-self-train', action='store_true')
    p.add_argument('--strong', type=float)
    p.add_argument('--model-floor', type=float)
    p.add_argument('--zero-shot-model')
    p.add_argument('--debug', action='store_true')
    # Calibration
    p.add_argument('--calibration', help='Temperature calibration JSON (key: temperature)')
    # Health
    p.add_argument('--strict', action='store_true', help='Fail if health status != 0')
    p.add_argument('--neutral-max', type=float, default=0.92)
    p.add_argument('--min-support', type=float, default=0.01)
    return p


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    out_dir = Path(a.outDir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = out_dir / 'pages.jsonl'
    insights_raw = out_dir / 'insights_raw.jsonl'
    classified = out_dir / 'insights_classified.jsonl'
    diagnostics = out_dir / 'diagnostics.json'
    health = out_dir / 'health.json'
    qualitative = out_dir / 'qualitative_examples.md'
    audit = out_dir / 'audit_evidence_labeltag.json'
    calibrated = out_dir / 'insights_classified_calibrated.jsonl'

    # 1. Scrape
    run([sys.executable, 'src/cli/scrape.py', '--url', a.url, '--out', str(pages), '--maxPages', str(a.maxPages), '--maxDepth', str(a.maxDepth), '--rps', str(a.rps), '--perPageLinkCap', str(a.perPageLinkCap)], 'scrape')

    # 2. Extract
    extract_cmd = [sys.executable, 'src/cli/extract_insights.py', '--pages', str(pages), '--out', str(insights_raw), '--minInsights', str(a.minInsights), '--maxInsights', str(a.maxInsights), '--minLen', str(a.minLen)]
    run(extract_cmd, 'extract')

    # 3. Classify
    classify_cmd = [sys.executable, 'src/cli/classify.py', '--in', str(insights_raw), '--out', str(classified)]
    if a.enable_zero_shot: classify_cmd.append('--enable-zero-shot')
    if a.enable_conflict_dampener: classify_cmd.append('--enable-conflict-dampener')
    if a.enable_margin_gating: classify_cmd.append('--enable-margin-gating')
    if a.enable_provisional_risk: classify_cmd.append('--enable-provisional-risk')
    if a.enable_self_train: classify_cmd.append('--enable-self-train')
    if a.strong is not None: classify_cmd += ['--strong', str(a.strong)]
    if a.model_floor is not None: classify_cmd += ['--model-floor', str(a.model_floor)]
    if a.zero_shot_model: classify_cmd += ['--zero-shot-model', a.zero_shot_model]
    if a.debug: classify_cmd.append('--debug')
    run(classify_cmd, 'classify')

    # 4. Diagnostics
    diag_out = run([sys.executable, 'scripts/diagnostics_summary.py', '--pred', str(classified)], 'diagnostics')
    diagnostics.write_text(diag_out, encoding='utf-8')

    # 5. Health
    health_out = run([sys.executable, 'scripts/check_health.py', '--pred', str(classified), '--neutral-max', str(a.neutral_max), '--min-support', str(a.min_support)], 'health')
    health.write_text(health_out, encoding='utf-8')
    health_json = json.loads(health_out)
    if a.strict and health_json.get('status', 0) != 0:
        sys.stderr.write('Strict health gate failed.\n')
        raise SystemExit(2)

    # 6. Qualitative examples
    run([sys.executable, 'scripts/qualitative_examples.py', '--pred', str(classified), '--out', str(qualitative)], 'qualitative')

    # 7. Evidence & tag audit
    run([sys.executable, 'scripts/audit_evidence_labeltag.py', '--raw', str(insights_raw), '--classified', str(classified), '--out', str(audit)], 'audit')

    # 8. Calibration (optional)
    calibrated_out = None
    if a.calibration:
        run([sys.executable, 'scripts/apply_calibration.py', '--predictions', str(classified), '--calibration', a.calibration, '--out', str(calibrated)], 'apply_calibration')
        calibrated_out = str(calibrated)

    summary = {
        'url': a.url,
        'outDir': str(out_dir.resolve()),
        'pages': str(pages),
        'insights_raw': str(insights_raw),
        'classified': str(classified),
        'diagnostics': str(diagnostics),
        'health': str(health),
        'qualitative_examples': str(qualitative),
        'audit': str(audit),
        'calibrated': calibrated_out,
        'strict_health_passed': health_json.get('passed', True),
    }
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':  # pragma: no cover
    main()
