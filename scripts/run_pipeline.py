"""High-level real-data pipeline runner.

Stages:
 1. Scrape (depth-limited crawl) -> pages.jsonl
 2. Extract atomic insights -> insights_raw.jsonl
 3. Classify insights -> insights_classified.jsonl (+ run_manifest.json)
 4. Diagnostics summary -> diagnostics.json
 5. Health check gate -> health.json (soft issues tolerated unless --strict)
 6. (Optional) Apply calibration (temperature scaling JSON) -> insights_classified_calibrated.jsonl

This is a convenience wrapper around existing CLI tools so a single
command can produce end-to-end artifacts for a seed URL.

Example (manual options):
    python scripts/run_pipeline.py \
        --url https://example.org --workDir out/example \
        --maxPages 40 --maxDepth 2 \
        --enable-zero-shot --enable-margin-gating --enable-conflict-dampener \
        --calibration calibration/temperature.json --strict

Convenience (auto workdir + common features + validation + summary):
    python scripts/run_pipeline.py --url https://example.org --all

Outputs (within workDir):
  pages.jsonl
  insights_raw.jsonl
  insights_classified.jsonl
  run_manifest.json (from classify stage)
  diagnostics.json
  health.json
  insights_classified_calibrated.jsonl (if calibration supplied)

Assumptions:
  - Environment dependencies already installed.
  - Zero-shot models will download on first use if enabled.
"""
from __future__ import annotations
import argparse, json, subprocess, sys, os, datetime
from pathlib import Path

# When running from an installed package (console script), __file__ will
# point inside site-packages. We want auto-workdir runs to land in the user's
# current working directory (where they invoked the command), not inside the
# library installation path. Retain original project root behavior when the
# repository source tree is detected (contains e.g. pyproject.toml).
_THIS_FILE = Path(__file__).resolve()
_PKG_ROOT = _THIS_FILE.parents[1]
_CWD = Path.cwd()

def _detect_source_tree() -> bool:
    # Heuristic: if pyproject.toml exists alongside scripts/ we are in source checkout
    return (_PKG_ROOT / 'pyproject.toml').exists() or (_PKG_ROOT / '.git').exists()

_SOURCE_MODE = _detect_source_tree()
if _SOURCE_MODE:
    ROOT = _PKG_ROOT
else:
    ROOT = _CWD  # always use invoking directory as logical output root when installed
    if str(_PKG_ROOT) not in sys.path:
        sys.path.insert(0, str(_PKG_ROOT))


def run(cmd: list[str], desc: str):
    """Run a subprocess command, raising on any non‑zero exit code."""
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"[{desc}] FAILED CMD: {' '.join(cmd)}\nSTDERR:\n{proc.stderr}\n")
        raise SystemExit(1)
    return proc.stdout.strip()

def _invoke(primary: list[str], fallback: list[str] | None, desc: str):
    """Try primary command; on failure optionally try fallback then re-raise with guidance."""
    try:
        return run(primary, desc)
    except SystemExit:
        if fallback:
            sys.stderr.write(f"[{desc}] primary strategy failed, attempting fallback...\n")
            return run(fallback, desc)
        raise


def build_parser():
    p = argparse.ArgumentParser(description="End-to-end real-data pipeline")
    p.add_argument('--url', required=True, help='Seed URL to crawl')
    p.add_argument('--workDir', help='Working directory for outputs (required unless --auto-workdir)')
    p.add_argument('--auto-workdir', action='store_true', help='Create timestamped workDir under ./out automatically')
    p.add_argument('--maxPages', type=int, default=50)
    p.add_argument('--maxDepth', type=int, default=2)
    p.add_argument('--rps', type=float, default=1.0)
    p.add_argument('--perPageLinkCap', type=int, default=25)
    # Extraction tuning
    p.add_argument('--minInsights', type=int, default=50)
    p.add_argument('--maxInsights', type=int, default=120)
    p.add_argument('--minLen', type=int, default=25)
    p.add_argument('--fuzzyDedupe', action='store_true')
    p.add_argument('--minhashFuzzy', action='store_true')
    # Classification toggles (map to classify.py flags)
    p.add_argument('--enable-zero-shot', action='store_true')
    p.add_argument('--zero-shot-primary', action='store_true')
    p.add_argument('--enable-margin-gating', action='store_true')
    p.add_argument('--enable-conflict-dampener', action='store_true')
    p.add_argument('--enable-provisional-risk', action='store_true')
    p.add_argument('--enable-self-train', action='store_true')
    p.add_argument('--model', help='Path to self-train model directory (model.pkl & vectorizer.pkl)')
    p.add_argument('--strong-threshold', type=float)
    p.add_argument('--risk-override-threshold', type=float)
    p.add_argument('--margin-threshold', type=float)
    p.add_argument('--conflict-dampener', type=float)
    p.add_argument('--model-floor', type=float)
    p.add_argument('--zero-shot-model', help='Override zero-shot model name')
    p.add_argument('--debug', action='store_true')
    # Calibration
    p.add_argument('--calibration', help='Path to temperature calibration JSON (expects key "temperature")')
    # Validation + summary helpers
    p.add_argument('--validate', action='store_true', help='Run delivery validation (strict) after health gate')
    p.add_argument('--summary-lines', type=int, default=3, help='Sample classified lines to show in final summary')
    # Bundle flag
    p.add_argument('--all', action='store_true', help='Enable common classifier features, auto workdir, validation, and human-friendly summary')
    # Health gating
    p.add_argument('--strict', action='store_true', help='Exit non-zero if health gate fails')
    p.add_argument('--minRiskPct', type=float, default=0.01, help='Minimum fraction of Risk to consider distribution healthy')
    p.add_argument('--maxNeutralPct', type=float, default=0.92, help='Maximum Neutral fraction before flagging imbalance')
    p.add_argument('--maxEntropyDrop', type=float, default=0.35, help='Maximum entropy deficit vs uniform (1 - H/Hmax)')
    return p


def main(argv=None):
    ap = build_parser()
    args = ap.parse_args(argv)

    # Expand bundle flag
    if args.all:
        if not args.enable_zero_shot: args.enable_zero_shot = True
        if not args.enable_margin_gating: args.enable_margin_gating = True
        if not args.enable_conflict_dampener: args.enable_conflict_dampener = True
        if not args.enable_provisional_risk: args.enable_provisional_risk = True
        if not args.enable_self_train: args.enable_self_train = True
        if not args.validate: args.validate = True
        if not args.auto_workdir: args.auto_workdir = True

    if not args.workDir and not args.auto_workdir:
        ap.error('Either --workDir must be provided or use --auto-workdir / --all')

    if args.auto_workdir:
        # Use timezone-aware UTC to avoid deprecation warning
        ts = datetime.datetime.now(datetime.UTC).strftime('%Y%m%d_%H%M%S')
        work = ROOT / 'out' / f'run_{ts}'
    else:
        work = Path(args.workDir)
    work.mkdir(parents=True, exist_ok=True)

    pages_path = work / 'pages.jsonl'
    insights_raw_path = work / 'insights_raw.jsonl'
    insights_classified_path = work / 'insights_classified.jsonl'
    diagnostics_path = work / 'diagnostics.json'
    health_path = work / 'health.json'

    # Startup diagnostic banner (written early so user sees execution context)
    sys.stderr.write(
        f"[pipeline] version={getattr(sys.modules.get('__main__'), '__package__', 'n/a')} source_mode={_SOURCE_MODE} output_root={ROOT}\n"
    )

    # 1. Scrape (module first, legacy fallback only in source mode)
    scrape_primary = [sys.executable, '-m', 'cli.scrape', '--url', args.url, '--out', str(pages_path), '--maxPages', str(args.maxPages), '--maxDepth', str(args.maxDepth), '--rps', str(args.rps), '--perPageLinkCap', str(args.perPageLinkCap)]
    scrape_fallback = [sys.executable, 'src/cli/scrape.py', '--url', args.url, '--out', str(pages_path), '--maxPages', str(args.maxPages), '--maxDepth', str(args.maxDepth), '--rps', str(args.rps), '--perPageLinkCap', str(args.perPageLinkCap)] if _SOURCE_MODE else None
    _invoke(scrape_primary, scrape_fallback, 'scrape')
    # Alias for spec naming (scraped_pages.jsonl) -> duplicate for compatibility
    scraped_alias = work / 'scraped_pages.jsonl'
    try:
        scraped_alias.write_bytes(pages_path.read_bytes())
    except Exception as e:
        sys.stderr.write(f"[warn] Failed to create alias scraped_pages.jsonl: {e}\n")

    # 2. Extract
    extract_cmd = [sys.executable, '-m', 'cli.extract_insights', '--pages', str(pages_path), '--out', str(insights_raw_path), '--minInsights', str(args.minInsights), '--maxInsights', str(args.maxInsights), '--minLen', str(args.minLen)]
    if args.fuzzyDedupe:
        extract_cmd.append('--fuzzyDedupe')
    if args.minhashFuzzy:
        extract_cmd.append('--minhashFuzzy')
    run(extract_cmd, 'extract')

    # 3. Classify
    classify_cmd = [sys.executable, '-m', 'cli.classify', '--in', str(insights_raw_path), '--out', str(insights_classified_path)]
    # map classification flags
    if args.enable_zero_shot: classify_cmd.append('--enable-zero-shot')
    if args.zero_shot_primary: classify_cmd.append('--zero-shot-primary')
    if args.enable_margin_gating: classify_cmd.append('--enable-margin-gating')
    if args.enable_conflict_dampener: classify_cmd.append('--enable-conflict-dampener')
    if args.enable_provisional_risk: classify_cmd.append('--enable-provisional-risk')
    if args.enable_self_train: classify_cmd.append('--enable-self-train')
    if args.model: classify_cmd += ['--model', args.model]
    if args.strong_threshold is not None: classify_cmd += ['--strong', str(args.strong_threshold)]
    if args.risk_override_threshold is not None: classify_cmd += ['--risk-override-threshold', str(args.risk_override_threshold)]
    if args.margin_threshold is not None: classify_cmd += ['--margin-threshold', str(args.margin_threshold)]
    if args.conflict_dampener is not None: classify_cmd += ['--conflict-dampener', str(args.conflict_dampener)]
    if args.model_floor is not None: classify_cmd += ['--model-floor', str(args.model_floor)]
    if args.zero_shot_model is not None: classify_cmd += ['--zero-shot-model', args.zero_shot_model]
    if args.debug: classify_cmd.append('--debug')
    run(classify_cmd, 'classify')

    # 4. Diagnostics summary
    # diagnostics_summary expects --pred not --predictions
    # diagnostics_summary lives under scripts/ still; attempt module first, fallback to script path.
    diag_cmd = [sys.executable, '-m', 'scripts.diagnostics_summary', '--pred', str(insights_classified_path)]
    diagnostics_out = run(diag_cmd, 'diagnostics')
    diagnostics_path.write_text(diagnostics_out, encoding='utf-8')

    # 5. Health check (tolerate exit code 1 unless --strict)
    neutral_max = args.maxNeutralPct
    health_cmd = [sys.executable, '-m', 'scripts.check_health', '--pred', str(insights_classified_path), '--neutral-max', str(neutral_max), '--min-support', str(args.minRiskPct)]
    if args.strict:
        health_cmd.append('--strict')
    proc = subprocess.run(health_cmd, capture_output=True, text=True)
    health_out = proc.stdout or '{}'
    # Always write whatever we received so users can inspect even on failure
    health_path.write_text(health_out, encoding='utf-8')
    try:
        health = json.loads(health_out)
    except json.JSONDecodeError:
        health = {'status': 3, 'error': 'malformed_health_output'}
    if args.strict and proc.returncode != 0:
        # Provide clear stderr context then abort
        sys.stderr.write('Health gate failed (strict mode, status != 0).\n')
        # Still emit a minimal JSON summary to stdout so automation can parse
        failure_summary = {
            'url': args.url,
            'workDir': str(work.resolve()),
            'health_status': health.get('status'),
            'health_issues': health.get('issues'),
            'error': 'health_fail_strict'
        }
        print(json.dumps(failure_summary, indent=2))
        raise SystemExit(2)

    # 6. Calibration application (optional)
    calibrated_path = None
    if args.calibration:
        calibrated_path = work / 'insights_classified_calibrated.jsonl'
        apply_cmd = [sys.executable, '-m', 'scripts.apply_calibration', '--predictions', str(insights_classified_path), '--calibration', args.calibration, '--out', str(calibrated_path)]
        run(apply_cmd, 'apply_calibration')

    summary = {
        'url': args.url,
        'workDir': str(work.resolve()),
        'pages': str(pages_path),
        'insights_raw': str(insights_raw_path),
        'classified': str(insights_classified_path),
        'diagnostics': str(diagnostics_path),
        'health': str(health_path),
        'health_status': health.get('status'),
        'calibrated': str(calibrated_path) if calibrated_path else None,
        'strict': args.strict,
    }
    # If validation requested, run after calibration step (so validator sees final artifacts)
    validation_status = None
    if args.validate:
        validate_cmd = [sys.executable, '-m', 'scripts.validate_delivery', '--workDir', str(work), '--check-rationale-len', '200', '--strict']
        val_proc = subprocess.run(validate_cmd, capture_output=True, text=True)
        try:
            validation_json = json.loads(val_proc.stdout or '{}')
            validation_status = validation_json.get('status')
        except Exception:
            validation_status = 'unknown'
        summary['validation_status'] = validation_status
        # Persist validation result
        try:
            (work / 'validation.json').write_text(val_proc.stdout or '{}', encoding='utf-8')
        except Exception as e:
            sys.stderr.write(f"[warn] could not write validation.json: {e}\n")

    # Derive label distribution from diagnostics.json
    label_dist = {}
    neutral_ratio = None
    try:
        diag_obj = json.loads(diagnostics_path.read_text(encoding='utf-8'))
        label_dist = diag_obj.get('label_dist') or {}
        neutral_ratio = diag_obj.get('neutral_ratio')
        summary['records'] = diag_obj.get('count')
    except Exception:
        pass
    summary['label_dist'] = label_dist
    summary['neutral_ratio'] = neutral_ratio

    # Count insights (raw) for convenience
    insight_count = None
    if insights_raw_path.exists():
        try:
            with insights_raw_path.open('r', encoding='utf-8') as f:
                insight_count = sum(1 for _ in f)
        except Exception:
            insight_count = None
    summary['insight_count'] = insight_count

    # Sample lines
    if args.summary_lines > 0 and insights_classified_path.exists():
        samples = []
        with insights_classified_path.open('r', encoding='utf-8') as f:
            for i, line in enumerate(f):
                if i >= args.summary_lines: break
                try:
                    rec = json.loads(line)
                    samples.append({
                        'label': rec.get('label'),
                        'confidence': rec.get('confidence'),
                        'text': (rec.get('text') or '')[:160]
                    })
                except Exception:
                    continue
        summary['samples'] = samples

    # Empty insights detection (extraction produced zero)
    if insights_raw_path.exists() and insights_raw_path.stat().st_size == 0:
        summary['empty_insights'] = True
        sys.stderr.write('[warn] extraction produced 0 insights (consider adjusting filters or thresholds)\n')

    # Human-readable banner when bundle or explicit summary options used
    if args.all or args.summary_lines:
        print('\n=== Pipeline Summary ===')
        print(f"URL: {args.url}")
        print(f"WorkDir: {work}")
        if summary.get('records') is not None:
            dist_str = ' '.join(f"{k}:{v}" for k,v in label_dist.items())
            print(f"Records: {summary.get('records')} ({dist_str})")
        if insight_count is not None:
            print(f"Insights (raw): {insight_count}")
        print(f"Health status: {summary.get('health_status')}")
        if validation_status is not None:
            print(f"Validation: {validation_status}")
        for s in summary.get('samples', []):
            print(f"  [{s['label']}] ({s['confidence']}) {s['text']}")
        print('========================\n')

    # Persist summary.json for easier consumption by external tooling
    try:
        (work / 'summary.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
    except Exception as e:  # pragma: no cover
        sys.stderr.write(f"[warn] could not write summary.json: {e}\n")

    # Always emit machine-parsable JSON last (stdout)
    print(json.dumps(summary, indent=2))


def main_all():  # pragma: no cover - convenience wrapper for tribute-e2e
    """Wrapper entrypoint that behaves like --all was supplied.

    This allows a zero‑thought single command after installation:
        tribute-e2e --url https://example.com
    Additional arguments can still override defaults (e.g. --maxPages 80).
    """
    # Inject --all if not already present
    argv = sys.argv[1:]
    if '--all' not in argv:
        argv = ['--all'] + argv
    main(argv)


if __name__ == '__main__':  # pragma: no cover
    main()
