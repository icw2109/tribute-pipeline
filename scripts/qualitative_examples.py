"""Generate qualitative_examples.md from predictions JSONL.

Selection logic:
  - Collect records with fields: text,label,confidence,labelTag,rationale,(optional)debug.provenance,provisionalLabel.
  - Top 3 high-confidence per label (Advantage,Risk,Neutral) sorted desc confidence.
  - Misclassifications:
       If ground truth label field 'trueLabel' present, pick up to 5 where label != trueLabel (highest confidence mistakes first).
       Else fallback to 5 'interesting' low-confidence or conflicting provenance examples:
          * low confidence (<=0.45) OR provisionalLabel present OR provenance contains multiple decision sources.
  - Emit markdown with sections.

Usage:
  python scripts/qualitative_examples.py --pred insights_classified.jsonl --out qualitative_examples.md
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path
from collections import defaultdict

TARGET_LABELS = ["Advantage","Risk","Neutral"]

def iter_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except Exception:
                continue

def pick_top(records, label, k=3):
    subset=[r for r in records if r.get('label')==label]
    subset.sort(key=lambda r: r.get('confidence',0.0), reverse=True)
    return subset[:k]

def pick_mis(recs, k=5):
    have_truth=[r for r in recs if 'trueLabel' in r]
    if have_truth:
        mismatches=[r for r in have_truth if r.get('label')!=r.get('trueLabel')]
        mismatches.sort(key=lambda r: r.get('confidence',0.0), reverse=True)
        return mismatches[:k]
    # heuristic fallback: low conf or provisional or multi-source provenance
    cand=[]
    for r in recs:
        conf=r.get('confidence',0.0)
        prov = (r.get('debug') or {}).get('provenance') if isinstance(r.get('debug'), dict) else None
        multi = isinstance(prov,list) and len(prov)>1
        if conf <= 0.45 or ('provisionalLabel' in r) or multi:
            cand.append(r)
    # sort by ascending confidence so the most uncertain first
    cand.sort(key=lambda r: r.get('confidence',0.0))
    return cand[:k]

def truncate(text: str, max_chars: int = 260) -> str:
    if len(text) <= max_chars:
        return text
    return text[:max_chars-3].rstrip() + '...'

def fmt_example(r):
    conf = r.get('confidence', 0.0)
    line = f"**Label:** {r.get('label')}  |  **Confidence:** {conf:.2f}  |  **Tag:** {r.get('labelTag','')}"
    if 'trueLabel' in r:
        line += f"  |  **True:** {r.get('trueLabel')}"
    rationale = truncate(r.get('rationale',''), 220)
    text = truncate(r.get('text',''), 400)
    prov_line_parts = []
    if isinstance(r.get('debug'), dict):
        prov = r['debug'].get('provenance')
        if isinstance(prov, list) and prov:
            prov_line_parts.append('Provenance: ' + ', '.join(prov))
    if 'provisionalLabel' in r:
        prov_line_parts.append('Provisional: ' + r['provisionalLabel'])
    if prov_line_parts:
        line += '  |  ' + '  |  '.join(prov_line_parts)
    return (
        f"- {line}\n\n"
        f"  > {text}\n\n"
        f"  _Rationale:_ {rationale}\n"
    )

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument('--pred', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--topK', type=int, default=3)
    ap.add_argument('--misK', type=int, default=5)
    args=ap.parse_args(argv)
    path=Path(args.pred)
    recs=list(iter_jsonl(path))
    if not recs:
        print('No records; aborting.', file=sys.stderr)
        return 1
    sections=[]
    sections.append('# Qualitative Examples')
    sections.append(f"Source file: `{path}`  Total records: {len(recs)}\n")
    # Top per label
    for lab in TARGET_LABELS:
        tops=pick_top(recs, lab, args.topK)
        sections.append(f"## Top {len(tops)} {lab} Examples")
        if not tops:
            sections.append("(none)")
        else:
            for r in tops:
                sections.append(fmt_example(r))
        sections.append("")
    # Misclassifications / Uncertain
    mis = pick_mis(recs, args.misK)
    title = 'Misclassifications' if mis and 'trueLabel' in mis[0] else 'Uncertain / Conflict Samples'
    sections.append(f"## {title}")
    if not mis:
        sections.append("(none)")
    else:
        for r in mis:
            sections.append(fmt_example(r))
    md='\n'.join(sections).rstrip()+'\n'
    Path(args.out).write_text(md, encoding='utf-8')
    print(f"Wrote {args.out}")
    return 0

if __name__=='__main__':  # pragma: no cover
    raise SystemExit(main())
