from __future__ import annotations
import argparse
import sys
from pathlib import Path
import sys, pathlib
# Ensure src root is on path if running as a script (python src/cli/scrape.py ...)
_root = pathlib.Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from core.crawl import crawl
from core.config import CrawlConfig
from core.iojsonl import write_jsonl
import json

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Depth-2 same-domain scraper")
    ap.add_argument("--url", required=True, help="Seed URL (starting point)")
    ap.add_argument("--maxDepth", type=int, default=2, help="Maximum crawl depth")
    ap.add_argument("--maxPages", type=int, default=50, help="Maximum number of pages")
    ap.add_argument("--rps", type=float, default=1.0, help="Requests per second (global cap)")
    ap.add_argument("--perPageLinkCap", type=int, default=25, help="Max outbound same-domain links considered per page (spec requirement)")
    ap.add_argument("--userAgent", default=None, help="Override User-Agent string (default from CrawlConfig)")
    ap.add_argument("--out", required=True, help="Output JSONL file path")
    ap.add_argument("--echo", action="store_true", help="Also print each JSON record to stdout as it's written")
    ap.add_argument("--stats", action="store_true", help="Print crawl stats JSON to stderr at end")
    ap.add_argument("--verbose", action="store_true", help="Print per-page / event decisions to stderr")
    ap.add_argument("--logEvents", help="Write JSONL event log to this file")
    ap.add_argument("--noContentDedupe", action="store_true", help="Disable content-based duplicate page detection")
    ap.add_argument("--maxHtmlBytes", type=int, help="Override maximum HTML size in bytes (default 800k; 0 to disable size guard)")
    ap.add_argument("--robotsFallbackAllow", action="store_true", help="Treat malformed robots.txt (HTML or empty) as allow-all")
    ap.add_argument("--extraScopeHost", help="Comma-separated additional hostnames treated as in-scope (exact + subdomains)")
    ap.add_argument("--browserHeaders", action="store_true", help="Send common browser Accept / Accept-Language headers for friendlier responses")
    args = ap.parse_args(argv)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    stats = {}
    event_log_file = None
    event_fp = None
    if args.logEvents:
        event_log_file = Path(args.logEvents)
        event_log_file.parent.mkdir(parents=True, exist_ok=True)
        event_fp = event_log_file.open('w', encoding='utf-8')

    def event_cb(ev):  # closure writes to stderr / file
        import json as _json, sys as _sys
        if args.verbose:
            _sys.stderr.write(_json.dumps(ev, ensure_ascii=False) + "\n")
        if event_fp:
            event_fp.write(_json.dumps(ev, ensure_ascii=False) + "\n")

    cfg = CrawlConfig(
        seed=args.url,
        max_depth=args.maxDepth,
        max_pages=args.maxPages,
        rps=args.rps,
        per_page_cap=args.perPageLinkCap,
        user_agent=args.userAgent or CrawlConfig.__dataclass_fields__['user_agent'].default,
        enable_content_dedupe=not args.noContentDedupe,
        max_html_bytes=(None if (args.maxHtmlBytes == 0) else args.maxHtmlBytes) if args.maxHtmlBytes is not None else None,
        robots_fallback_allow=args.robotsFallbackAllow,
        extra_scope_hosts=tuple(h.strip().lower() for h in args.extraScopeHost.split(',')) if args.extraScopeHost else (),
        browser_headers=args.browserHeaders,
    )
    records_iter = crawl(
        config=cfg,
        stats=stats,
        event_cb=event_cb if (args.verbose or event_fp) else None,
    )
    if args.echo:
        with open(out_path, "w", encoding="utf-8") as f:
            for rec in records_iter:
                line = json.dumps(rec, ensure_ascii=False)
                f.write(line + "\n")
                print(line)
    else:
        write_jsonl(records_iter, str(out_path))
    if event_fp:
        event_fp.close()
    if args.stats:
        import sys as _sys, json as _json
        _sys.stderr.write(_json.dumps(stats) + "\n")
    return 0

if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
