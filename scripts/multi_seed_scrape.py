"""Multi-seed scraper wrapper.

Purpose: When some target subdomains don't expose links (due to JS or blocking),
invoking individual scrapes and merging outputs ensures coverage of all
prescribed in-scope hosts (e.g., main site + docs + blog).

Usage:
  python scripts/multi_seed_scrape.py \
    --seeds https://www.eigenlayer.xyz,https://docs.eigenlayer.xyz,https://blog.eigenlayer.xyz \
    --out pages_eigenlayer_all.jsonl --maxPagesPerSeed 25 --maxDepth 2 --rps 1 \
    --robotsFallbackAllow --browserHeaders

Behavior:
  * Runs scrape.py once per seed with provided arguments.
  * Merges results in memory, de-duplicating by canonical URL (earliest win).
  * Writes a unified JSONL containing merged pages.
  * Emits a summary JSON (counts per seed, total unique).

Notes:
  * Per-seed page cap: `--maxPagesPerSeed` so aggregate may exceed spec max unless you lower it; tune to keep combined under 50 if required (e.g., 18+16+16).
  * Use downstream truncate if needed.
"""
from __future__ import annotations
import argparse, subprocess, sys, json, tempfile, random, time
from pathlib import Path


def run(cmd: list[str], desc: str):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.stderr.write(f"[{desc}] FAILED: {' '.join(cmd)}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}\n")
        raise SystemExit(1)
    return proc


def build_parser():
    p = argparse.ArgumentParser(description='Multi-seed merge scraper')
    p.add_argument('--seeds', required=True, help='Comma-separated seed URLs')
    p.add_argument('--out', required=True, help='Merged pages JSONL output path')
    p.add_argument('--maxPagesPerSeed', type=int, default=20)
    p.add_argument('--maxDepth', type=int, default=2)
    p.add_argument('--rps', type=float, default=1.0)
    p.add_argument('--perPageLinkCap', type=int, default=25)
    p.add_argument('--robotsFallbackAllow', action='store_true')
    p.add_argument('--browserHeaders', action='store_true')
    p.add_argument('--userAgent', help='Override user agent')
    p.add_argument('--verbose', action='store_true')
    p.add_argument('--uaRotate', help='Comma-separated list of user-agents to rotate per seed (overrides single --userAgent)')
    p.add_argument('--stealthJitter', type=float, default=0.0, help='Random sleep (0..stealthJitter) seconds before each seed scrape to vary timing')
    p.add_argument('--pivotFallback', help='Comma-separated list of alternate pivot seeds to try if all primary seeds yield 0 pages')
    return p


def main(argv=None):
    ap = build_parser()
    a = ap.parse_args(argv)
    seeds = [s.strip() for s in a.seeds.split(',') if s.strip()]
    out_path = Path(a.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix='multi_seed_scrape_'))
    per_seed_files = []
    per_seed_counts = {}

    ua_list = [u.strip() for u in (a.uaRotate.split(',') if a.uaRotate else []) if u.strip()]
    # Primary pass
    for idx, seed in enumerate(seeds):
        seed_safe = seed.replace('://', '_').replace('/', '_')[:60]
        seed_out = tmp_dir / f'{seed_safe}.jsonl'
        if a.stealthJitter > 0:
            time.sleep(random.uniform(0, a.stealthJitter))
        cmd = [sys.executable, 'src/cli/scrape.py', '--url', seed, '--out', str(seed_out), '--maxPages', str(a.maxPagesPerSeed), '--maxDepth', str(a.maxDepth), '--rps', str(a.rps), '--perPageLinkCap', str(a.perPageLinkCap)]
        if a.robotsFallbackAllow: cmd.append('--robotsFallbackAllow')
        if a.browserHeaders: cmd.append('--browserHeaders')
        # UA rotation precedence > single UA param
        if ua_list:
            ua = ua_list[idx % len(ua_list)]
            cmd += ['--userAgent', ua]
        elif a.userAgent:
            cmd += ['--userAgent', a.userAgent]
        if a.verbose: cmd.append('--verbose')
        run(cmd, f'scrape({seed})')
        per_seed_files.append(seed_out)
        # count lines
        try:
            with seed_out.open('r', encoding='utf-8') as f:
                per_seed_counts[seed] = sum(1 for _ in f)
        except FileNotFoundError:
            per_seed_counts[seed] = 0

    total_primary = sum(per_seed_counts.values())
    pivot_used = False
    pivot_details = []
    if total_primary == 0 and a.pivotFallback:
        pivot_used = True
        pivot_seeds = [s.strip() for s in a.pivotFallback.split(',') if s.strip()]
        for idx, seed in enumerate(pivot_seeds):
            seed_safe = seed.replace('://', '_').replace('/', '_')[:60]
            seed_out = tmp_dir / f'pivot_{seed_safe}.jsonl'
            if a.stealthJitter > 0:
                time.sleep(random.uniform(0, a.stealthJitter))
            cmd = [sys.executable, 'src/cli/scrape.py', '--url', seed, '--out', str(seed_out), '--maxPages', str(a.maxPagesPerSeed), '--maxDepth', str(a.maxDepth), '--rps', str(a.rps), '--perPageLinkCap', str(a.perPageLinkCap)]
            if a.robotsFallbackAllow: cmd.append('--robotsFallbackAllow')
            if a.browserHeaders: cmd.append('--browserHeaders')
            if ua_list:
                ua = ua_list[(idx + len(seeds)) % len(ua_list)]
                cmd += ['--userAgent', ua]
            elif a.userAgent:
                cmd += ['--userAgent', a.userAgent]
            if a.verbose: cmd.append('--verbose')
            run(cmd, f'pivot_scrape({seed})')
            per_seed_files.append(seed_out)
            try:
                with seed_out.open('r', encoding='utf-8') as f:
                    cnt = sum(1 for _ in f)
            except FileNotFoundError:
                cnt = 0
            per_seed_counts[seed] = cnt
            pivot_details.append({'seed': seed, 'count': cnt})

    # Merge & dedupe (first occurrence kept)
    seen = set()
    merged = []
    for fp in per_seed_files:
        if not fp.exists():
            continue
        with fp.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                url = rec.get('url')
                if not url or url in seen:
                    continue
                seen.add(url)
                merged.append(rec)

    with out_path.open('w', encoding='utf-8') as out_f:
        for rec in merged:
            out_f.write(json.dumps(rec) + '\n')

    summary = {
        'seeds': seeds,
        'per_seed_counts': per_seed_counts,
        'unique_pages': len(merged),
        'output': str(out_path.resolve()),
        'pivot_used': pivot_used,
        'pivot_details': pivot_details,
        'ua_rotation': bool(ua_list),
        'note': 'Adjust maxPagesPerSeed to ensure combined unique pages <= spec max if strict compliance needed.'
    }
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':  # pragma: no cover
    main()
