#!/usr/bin/env python
"""Validate labeled JSONL against annotation schema & guidelines.

Checks:
  - Required fields present
  - label in allowed set
  - taxonomyVersion consistent
  - Optional rationale_gold length constraint (< 160 chars)
  - No duplicated text entries
Exit with code 1 on validation failure.
"""
import argparse, json, sys
from pathlib import Path

REQUIRED = [
    'id','text','label','sourceUrl','candidateType','provenance','sample_phase','annotator','taxonomyVersion'
]
LABELS = {'Advantage','Risk','Neutral'}

def iter_jsonl(p: Path):
    with p.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip();
            if not line: continue
            try: yield json.loads(line)
            except: pass

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--taxonomy-version', default=None)
    args=ap.parse_args()

    rows=list(iter_jsonl(Path(args.inp)))
    errors=[]
    seen_text=set()
    taxonomy_version_expected = args.taxonomy_version
    for idx,r in enumerate(rows):
        for k in REQUIRED:
            if k not in r:
                errors.append(f"row {idx} missing field {k}")
        if r.get('label') and r['label'] not in LABELS:
            errors.append(f"row {idx} invalid label {r.get('label')}")
        if r.get('rationale_gold') and len(r['rationale_gold'])>160:
            errors.append(f"row {idx} rationale_gold too long")
        txt = r.get('text')
        if txt in seen_text:
            errors.append(f"duplicate text at row {idx}")
        else:
            seen_text.add(txt)
        if taxonomy_version_expected and r.get('taxonomyVersion') != taxonomy_version_expected:
            errors.append(f"row {idx} taxonomyVersion mismatch {r.get('taxonomyVersion')}")
    if errors:
        print(json.dumps({'status':'fail','errors':errors}, indent=2))
        sys.exit(1)
    print(json.dumps({'status':'ok','count':len(rows)}))

if __name__ == '__main__':
    main()
