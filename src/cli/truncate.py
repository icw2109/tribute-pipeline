from __future__ import annotations
import argparse, sys, json, pathlib

# Simple truncation tool: copies first N JSONL records, optionally truncating text field to max chars.

import sys, pathlib
_root = pathlib.Path(__file__).resolve().parents[1]
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from core.iojsonl import read_jsonl

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Truncate a JSONL file to first N records; optionally shorten text")
    ap.add_argument('--in', dest='inp', required=True, help='Input JSONL path')
    ap.add_argument('--out', dest='out', required=True, help='Output JSONL path')
    ap.add_argument('--limit', type=int, default=5, help='Number of records to keep')
    ap.add_argument('--maxTextChars', type=int, default=400, help='Max characters for text field (0 = no trim)')
    ap.add_argument('--pretty', action='store_true', help='Pretty print to stdout as well')
    args = ap.parse_args(argv)

    inp = pathlib.Path(args.inp)
    if not inp.exists():
        print(f"Input not found: {inp}", file=sys.stderr)
        return 1
    outp = pathlib.Path(args.out)
    outp.parent.mkdir(parents=True, exist_ok=True)

    written = 0
    with outp.open('w', encoding='utf-8') as fout:
        for rec in read_jsonl(str(inp)):
            if written >= args.limit:
                break
            if args.maxTextChars > 0 and isinstance(rec.get('text'), str):
                if len(rec['text']) > args.maxTextChars:
                    rec['text'] = rec['text'][:args.maxTextChars] + '…'
            fout.write(json.dumps(rec, ensure_ascii=False) + '\n')
            if args.pretty:
                print(json.dumps(rec, ensure_ascii=False, indent=2)[:800])
            written += 1
    print(f"Wrote {written} records -> {outp}")
    return 0

if __name__ == '__main__':  # pragma: no cover
    raise SystemExit(main())
