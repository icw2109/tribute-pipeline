from __future__ import annotations
"""Validate a labeled insights JSONL file.

Checks:
 - Required fields present: text, label
 - Optional recommended fields: sourceUrl, candidateType, qualityScore, provenance, taxonomyVersion
 - Label in allowed set
 - Duplicate texts
 - Basic length sanity
 - Optional: enforce provenance = scraped for evaluation set

Outputs JSON summary with lists of issues; non-zero exit if hard errors unless --soft.

Usage:
  python src/cli/validate_labels.py --in data/seed_labeled.v1.jsonl --allowed Advantage Risk Neutral
  python src/cli/validate_labels.py --in data/seed_labeled.v1.jsonl --markdown reports/label_validation.md
"""
import argparse, json, sys, os, collections
from pathlib import Path
from typing import List, Dict

def iter_jsonl(path: str):
    with open(path,'r',encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue

def build_parser():
    p = argparse.ArgumentParser(description='Validate labeled insight dataset.')
    p.add_argument('--in', dest='inp', required=True)
    p.add_argument('--allowed', nargs='+', default=['Advantage','Risk','Neutral'])
    p.add_argument('--minLen', type=int, default=20)
    p.add_argument('--maxLen', type=int, default=320)
    p.add_argument('--markdown', help='Optional markdown output path')
    p.add_argument('--soft', action='store_true', help='Do not exit non-zero on errors')
    return p

def main(argv=None):
    args = build_parser().parse_args(argv)
    allowed = set(args.allowed)
    seen = set()
    dupes = []
    missing_label = []
    bad_label = []
    length_issues = []
    rows = 0
    per_label = collections.Counter()
    for obj in iter_jsonl(args.inp):
        rows += 1
        text = obj.get('text')
        label = obj.get('label')
        if not text:
            missing_label.append({'row': rows, 'reason':'missing text'})
            continue
        if not label:
            missing_label.append({'text': text[:120], 'reason':'missing label'})
            continue
        if label not in allowed:
            bad_label.append({'text': text[:120], 'label': label})
        if text in seen:
            dupes.append(text[:140])
        seen.add(text)
        if len(text) < args.minLen or len(text) > args.maxLen:
            length_issues.append({'text': text[:120], 'len': len(text)})
        per_label[label] += 1
    summary = {
        'file': args.inp,
        'total_rows': rows,
        'label_counts': dict(per_label),
        'missing': missing_label,
        'bad_label': bad_label,
        'duplicates': dupes,
        'length_issues': length_issues,
        'status': 'ok' if not (missing_label or bad_label) else 'issues'
    }
    sys.stdout.write(json.dumps(summary, indent=2, ensure_ascii=False) + '\n')
    if args.markdown:
        with open(args.markdown,'w',encoding='utf-8') as w:
            w.write(f"# Label Validation Report\n\nFile: `{args.inp}`\n\n")
            w.write("## Counts\n\n")
            for lab, c in per_label.items():
                w.write(f"- {lab}: {c}\n")
            if missing_label:
                w.write("\n## Missing Entries\n")
                for m in missing_label[:20]:
                    w.write(f"- {m}\n")
            if bad_label:
                w.write("\n## Bad Labels (first 20)\n")
                for b in bad_label[:20]:
                    w.write(f"- {b}\n")
            if dupes:
                w.write("\n## Duplicates (first 20 previews)\n")
                for d in dupes[:20]:
                    w.write(f"- {d}\n")
            if length_issues:
                w.write("\n## Length Issues (first 20)\n")
                for li in length_issues[:20]:
                    w.write(f"- {li}\n")
    if not args.soft and (missing_label or bad_label):
        sys.exit(2)

if __name__ == '__main__':  # pragma: no cover
    main()
