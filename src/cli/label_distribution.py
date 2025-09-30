from __future__ import annotations
"""Summarize label distribution across one or more labeled JSONL files.

Usage:
  python src/cli/label_distribution.py --files data/splits/train.jsonl data/splits/dev.jsonl --markdown reports/label_distribution.md

If multiple files provided, per-file counts + overall percentages are shown.

Outputs JSON summary to stdout; optional Markdown table.
"""
import argparse, json, sys, os, collections
from pathlib import Path

def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def count_file(path: str):
    ctr = collections.Counter()
    total = 0
    for obj in iter_jsonl(path):
        lab = obj.get('label')
        txt = obj.get('text')
        if not lab or not txt:
            continue
        ctr[lab] += 1
        total += 1
    return total, ctr

def build_parser():
    p = argparse.ArgumentParser(description='Summarize label distributions.')
    p.add_argument('--files', nargs='+', required=True, help='One or more labeled JSONL files.')
    p.add_argument('--markdown', help='Optional markdown output path')
    return p

def main(argv=None):
    args = build_parser().parse_args(argv)
    overall = collections.Counter()
    file_summaries = []
    grand_total = 0
    for f in args.files:
        total, ctr = count_file(f)
        grand_total += total
        overall.update(ctr)
        file_summaries.append({'file': f, 'total': total, 'counts': dict(ctr)})
    pct = {lab: round(100.0 * c / grand_total,2) for lab, c in overall.items()} if grand_total else {}
    summary = {
        'files': file_summaries,
        'overall_total': grand_total,
        'overall_counts': dict(overall),
        'overall_pct': pct
    }
    sys.stdout.write(json.dumps(summary, indent=2) + '\n')
    if args.markdown:
        with open(args.markdown,'w',encoding='utf-8') as w:
            w.write('# Label Distribution\n\n')
            for fs in file_summaries:
                w.write(f"## {fs['file']} (n={fs['total']})\n\n")
                for lab, c in fs['counts'].items():
                    w.write(f"- {lab}: {c}\n")
                w.write('\n')
            w.write('## Overall\n\n')
            for lab, c in overall.items():
                w.write(f"- {lab}: {c} ({pct.get(lab,0)}%)\n")
    # Exit success

if __name__ == '__main__':  # pragma: no cover
    main()
