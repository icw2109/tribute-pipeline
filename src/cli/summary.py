from __future__ import annotations
import argparse, json
from pathlib import Path
import sys, pathlib
_root = pathlib.Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from core.iojsonl import read_jsonl

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Summarize a scraped JSONL file")
    ap.add_argument("path", help="Path to JSONL file")
    ap.add_argument("--show", type=int, default=0, help="Show first N records inline")
    args = ap.parse_args(argv)

    p = Path(args.path)
    if not p.exists():
        print(f"File not found: {p}")
        return 1

    count = 0
    depths = {}
    domains = {}
    first_records = []

    for rec in read_jsonl(str(p)):
        count += 1
        d = rec.get("depth")
        depths[d] = depths.get(d, 0) + 1
        url = rec.get("url", "")
        host = ""
        try:
            from urllib.parse import urlparse
            host = urlparse(url).hostname or ""
        except Exception:
            pass
        domains[host] = domains.get(host, 0) + 1
        if args.show and len(first_records) < args.show:
            first_records.append(rec)

    print("Total records:", count)
    print("Depth distribution:", depths)
    print("Domains:", domains)
    if first_records:
        print("\nSample records:")
        for r in first_records:
            print(json.dumps(r, ensure_ascii=False)[:400])
    return 0

if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
