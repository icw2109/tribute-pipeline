"""One-shot demonstration script for the real workflow.

Runs: scrape -> extract -> classify -> diagnostics -> health -> qualitative -> audit.
Outputs placed in a timestamped directory under out/ (default root).

Usage:
  python scripts/quick_demo.py --url https://www.eigenlayer.xyz
  python scripts/quick_demo.py --url https://www.eigenlayer.xyz --zero-shot --self-train

This is a convenience wrapper with fewer flags than run_pipeline/regenerate_artifacts.
"""
from __future__ import annotations
import argparse, subprocess, sys, json, datetime
from pathlib import Path


def sh(cmd: list[str], desc: str):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"[{desc}] FAILED: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n")
        raise SystemExit(1)
    return proc.stdout


def build_parser():
    p = argparse.ArgumentParser(description='Quick end-to-end demo runner')
    p.add_argument('--url', required=True)
    p.add_argument('--outRoot', default='out', help='Root output directory')
    p.add_argument('--maxPages', type=int, default=30)
    p.add_argument('--maxDepth', type=int, default=2)
    p.add_argument('--rps', type=float, default=1.0)
    p.add_argument('--minInsights', type=int, default=50)
    p.add_argument('--maxInsights', type=int, default=110)
    p.add_argument('--minPages', type=int, default=3, help='Fail (or fallback) if fewer pages than this captured')
    p.add_argument('--fallbackSeed', default='https://example.com', help='Backup seed if primary yields 0 pages')
    p.add_argument('--allow-fallback', action='store_true', help='Enable retry with fallback seed when 0 pages scraped')
    p.add_argument('--robots-fallback-allow', action='store_true', help='Treat malformed robots responses as allow-all')
    p.add_argument('--user-agent', help='Override User-Agent string for crawl')
    p.add_argument('--browser-headers', action='store_true', help='Send common browser Accept/Language headers')
    p.add_argument('--eigen-mode', action='store_true', help='Use preset multi-seed EigenLayer domains (main, docs, blog)')
    p.add_argument('--seeds', help='Comma-separated override seeds for multi-seed scraping (implies eigen-mode style).')
    p.add_argument('--ua-rotate', help='Comma-separated user agent list (overrides single user-agent) for multi-seed mode.')
    p.add_argument('--stealth-jitter', type=float, default=0.0, help='Random sleep 0..J seconds before each seed fetch (multi-seed).')
    p.add_argument('--pivot-fallback', help='Comma-separated alternate site seeds if primary multi-seed yields 0 pages (e.g. lido.fi,polkadot.network).')
    p.add_argument('--verbose', action='store_true', help='Verbose crawl events')
    p.add_argument('--zero-shot', action='store_true')
    p.add_argument('--self-train', action='store_true')
    p.add_argument('--margin-gating', action='store_true')
    p.add_argument('--conflict-dampener', action='store_true')
    p.add_argument('--provisional-risk', action='store_true')
    p.add_argument('--strict-health', action='store_true')
    return p


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)

    ts = datetime.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out_dir = Path(a.outRoot) / f'demo_{ts}'
    out_dir.mkdir(parents=True, exist_ok=True)

    pages = out_dir / 'pages.jsonl'
    raw_insights = out_dir / 'insights_raw.jsonl'
    classified = out_dir / 'insights_classified.jsonl'
    diagnostics = out_dir / 'diagnostics.json'
    health = out_dir / 'health.json'
    qualitative = out_dir / 'qualitative_examples.md'
    audit = out_dir / 'audit_evidence_labeltag.json'

    def run_scrape(seed: str):
        cmd = [sys.executable, 'src/cli/scrape.py', '--url', seed, '--out', str(pages), '--maxPages', str(a.maxPages), '--maxDepth', str(a.maxDepth), '--rps', str(a.rps)]
        if a.robots_fallback_allow: cmd.append('--robotsFallbackAllow')
        if a.verbose: cmd.append('--verbose')
        if a.user_agent: cmd += ['--userAgent', a.user_agent]
        if a.browser_headers: cmd.append('--browserHeaders')
        sh(cmd, f'scrape({seed})')

    used_fallback = False
    multi_seed = []
    if a.eigen_mode:
        multi_seed = [
            a.url,  # user provided (should be main)
            'https://docs.eigenlayer.xyz',
            'https://blog.eigenlayer.xyz',
            # Some deployments use eigencloud domains (observed in live HTML)
            'https://docs.eigencloud.xyz',
            'https://blog.eigencloud.xyz'
        ]
    if a.seeds:
        multi_seed = [s.strip() for s in a.seeds.split(',') if s.strip()]

    if multi_seed:
        # Use multi_seed_scrape helper
        tmp_pages = pages  # final output file
        cmd = [sys.executable, 'scripts/multi_seed_scrape.py', '--seeds', ','.join(multi_seed), '--out', str(tmp_pages), '--maxDepth', str(a.maxDepth), '--rps', str(a.rps)]
        # Derive per-seed cap to approximate maxPages (simple division); ensure >=1
        per_seed_cap = max(1, a.maxPages // max(1, len(multi_seed)))
        cmd += ['--maxPagesPerSeed', str(per_seed_cap)]
        cmd += ['--perPageLinkCap', '25']
        if a.robots_fallback_allow: cmd.append('--robotsFallbackAllow')
        if a.browser_headers: cmd.append('--browserHeaders')
        if a.user_agent: cmd += ['--userAgent', a.user_agent]
        if a.ua_rotate: cmd += ['--uaRotate', a.ua_rotate]
        if a.stealth_jitter: cmd += ['--stealthJitter', str(a.stealth_jitter)]
        if a.pivot_fallback: cmd += ['--pivotFallback', a.pivot_fallback]
        if a.verbose: cmd.append('--verbose')
        sh(cmd, 'multi_seed_scrape')
    else:
        # Single seed path
        run_scrape(a.url)
        page_count = sum(1 for _ in pages.open('r', encoding='utf-8')) if pages.exists() else 0
        if page_count == 0 and a.allow_fallback:
            sys.stderr.write(f'[warn] 0 pages from primary seed {a.url}; retrying with fallback {a.fallbackSeed}\n')
            run_scrape(a.fallbackSeed)
            page_count = sum(1 for _ in pages.open('r', encoding='utf-8')) if pages.exists() else 0
            used_fallback = True

    # Count pages after whichever path
    page_count = sum(1 for _ in pages.open('r', encoding='utf-8')) if pages.exists() else 0
    if page_count < a.minPages:
        summary = {
            'error': 'insufficient_pages',
            'page_count': page_count,
            'minPages': a.minPages,
            'used_fallback': used_fallback,
            'multi_seed': bool(multi_seed),
            'seeds': multi_seed or [a.url],
            'url': a.url,
            'fallbackSeed': a.fallbackSeed if a.allow_fallback else None,
            'out_dir': str(out_dir.resolve()),
        }
        print(json.dumps(summary, indent=2))
        raise SystemExit(3)

    # 2. Extract
    sh([sys.executable, 'src/cli/extract_insights.py', '--pages', str(pages), '--out', str(raw_insights), '--minInsights', str(a.minInsights), '--maxInsights', str(a.maxInsights)], 'extract')
    raw_count = sum(1 for _ in raw_insights.open('r', encoding='utf-8')) if raw_insights.exists() else 0
    if raw_count == 0:
        summary = {
            'error': 'no_insights',
            'page_count': page_count,
            'insight_count': 0,
            'url': a.url,
            'used_fallback': used_fallback,
            'out_dir': str(out_dir.resolve()),
        }
        print(json.dumps(summary, indent=2))
        raise SystemExit(4)

    # 3. Classify
    classify_cmd = [sys.executable, 'src/cli/classify.py', '--in', str(raw_insights), '--out', str(classified)]
    if a.zero_shot: classify_cmd.append('--enable-zero-shot')
    if a.self_train: classify_cmd.append('--enable-self-train')
    if a.margin_gating: classify_cmd.append('--enable-margin-gating')
    if a.conflict_dampener: classify_cmd.append('--enable-conflict-dampener')
    if a.provisional_risk: classify_cmd.append('--enable-provisional-risk')
    sh(classify_cmd, 'classify')

    # 4. Diagnostics
    diag_out = sh([sys.executable, 'scripts/diagnostics_summary.py', '--pred', str(classified)], 'diagnostics')
    diagnostics.write_text(diag_out, encoding='utf-8')

    # 5. Health
    # Health: if non-strict, allow continuation even on issues (exit code swallowed)
    health_cmd = [sys.executable, 'scripts/check_health.py', '--pred', str(classified)]
    if a.strict_health:
        health_cmd.append('--strict')
    proc = subprocess.run(health_cmd, capture_output=True, text=True)
    health_out = proc.stdout or '{}'
    health.write_text(health_out, encoding='utf-8')
    try:
        health_json = json.loads(health_out)
    except json.JSONDecodeError:
        health_json = {'status': 3, 'error': 'malformed_health_output'}
    if a.strict_health and proc.returncode != 0:
        sys.stderr.write('Strict health gate failed (status !=0).\n')
        # Still emit final summary but mark failure in summary
        failure_summary = {
            'url': a.url,
            'health_status': health_json.get('status'),
            'health_issues': health_json.get('issues'),
            'error': 'health_fail_strict',
            'out_dir': str(out_dir.resolve())
        }
        print(json.dumps(failure_summary, indent=2))
        raise SystemExit(2)

    # 6. Qualitative examples
    sh([sys.executable, 'scripts/qualitative_examples.py', '--pred', str(classified), '--out', str(qualitative)], 'qualitative')

    # 7. Audit
    sh([sys.executable, 'scripts/audit_evidence_labeltag.py', '--raw', str(raw_insights), '--classified', str(classified), '--out', str(audit)], 'audit')

    classified_count = sum(1 for _ in classified.open('r', encoding='utf-8')) if classified.exists() else 0
    summary = {
        'url': a.url,
        'used_fallback': used_fallback,
        'out_dir': str(out_dir.resolve()),
        'pages_file': str(pages),
        'page_count': page_count,
        'insights_raw_file': str(raw_insights),
        'insight_count': raw_count,
        'classified_file': str(classified),
        'classified_count': classified_count,
        'diagnostics': str(diagnostics),
        'health': str(health),
        'qualitative_examples': str(qualitative),
        'audit': str(audit),
        'health_status': health_json.get('status', 0),
    }
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':  # pragma: no cover
    main()
