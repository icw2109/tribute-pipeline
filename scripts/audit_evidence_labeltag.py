"""Audit evidence arrays in raw insights and labelTag presence in classified outputs.

Outputs JSON to stdout and optionally a file with:
  raw_total, raw_missing_evidence, raw_empty_evidence
  classified_total, classified_missing_labelTag, classified_empty_labelTag, classified_missing_label
  label_distribution

Usage:
  python scripts/audit_evidence_labeltag.py --raw insights_raw.jsonl --classified insights_classified.jsonl --out audit_evidence_labeltag.json
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

def iter_jsonl(path: Path):
    if not path.exists():
        return []
    out=[]
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                out.append(json.loads(line))
            except Exception:
                pass
    return out

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--raw', required=True)
    ap.add_argument('--classified', required=True)
    ap.add_argument('--out')
    args=ap.parse_args(argv)
    raw_path=Path(args.raw)
    cls_path=Path(args.classified)
    raw_recs=iter_jsonl(raw_path)
    cls_recs=iter_jsonl(cls_path)

    raw_missing=0; raw_empty=0
    for r in raw_recs:
        evid = r.get('evidence')
        if evid is None:
            raw_missing += 1
        elif isinstance(evid, list) and len(evid)==0:
            raw_empty += 1

    cls_missing_tag=0; cls_empty_tag=0; cls_missing_label=0
    label_dist={}
    for r in cls_recs:
        lab=r.get('label')
        if lab is None:
            cls_missing_label += 1
        else:
            label_dist[lab]=label_dist.get(lab,0)+1
        tag=r.get('labelTag')
        if tag is None:
            cls_missing_tag += 1
        elif isinstance(tag,str) and tag.strip()=='' :
            cls_empty_tag += 1

    out = {
        'raw_total': len(raw_recs),
        'raw_missing_evidence': raw_missing,
        'raw_empty_evidence': raw_empty,
        'classified_total': len(cls_recs),
        'classified_missing_labelTag': cls_missing_tag,
        'classified_empty_labelTag': cls_empty_tag,
        'classified_missing_label': cls_missing_label,
        'label_distribution': label_dist,
    }
    js=json.dumps(out, indent=2)
    print(js)
    if args.out:
        Path(args.out).write_text(js, encoding='utf-8')

if __name__=='__main__':  # pragma: no cover
    main()
