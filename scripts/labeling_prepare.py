#!/usr/bin/env python
"""Prepare a sampling of raw insights for human labeling.

Input: insights_raw.jsonl (fields: text, sourceUrl, ...)
Output: data/labeling_batch.v1.jsonl with added fields for annotation.

Sampling strategy:
  * Optional max count
  * Optional stratified emphasis by presence of risk / advantage cue keywords

Each output line includes required annotation schema placeholders.
"""
import argparse, json, random, re
from pathlib import Path
from datetime import datetime

ADV_CUES = re.compile(r"\b(growth|increase|scal|adopt|improv|efficien|expand|partner|revenue)\b", re.I)
RISK_CUES = re.compile(r"\b(risk|attack|slash|penalt|exploit|outage|fail|downtime|vulnerab|issue)\b", re.I)

ANNOTATION_SCHEMA = {
    "id": None,
    "text": None,
    "label": None,
    "sourceUrl": None,
    "candidateType": None,
    "qualityScore": None,
    "provenance": "scraped",
    "sample_phase": None,
    "annotator": None,
    "taxonomyVersion": None,
    "rationale_gold": None,
    "notes": None
}

def iter_jsonl(path: Path):
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                yield json.loads(line)
            except: continue


def classify_candidate_type(text: str) -> str:
    if RISK_CUES.search(text):
        return 'risk'
    if ADV_CUES.search(text):
        return 'advantage'
    if re.search(r"\b(token|supply|emission|tvl|stake|validator)\b", text, re.I):
        return 'tokenomics'
    if re.search(r"\b(user|customer|operator|partner)\b", text, re.I):
        return 'adoption'
    return 'other'


def score_quality(text: str) -> float:
    # Simple heuristic: presence of numbers + length window
    has_num = bool(re.search(r"\d", text))
    length = len(text)
    base = 0.5 + 0.2*has_num
    if 40 <= length <= 180:
        base += 0.2
    if RISK_CUES.search(text) or ADV_CUES.search(text):
        base += 0.1
    return round(min(base,1.0),3)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--in', dest='inp', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--max', type=int, default=150)
    ap.add_argument('--seed', type=int, default=42)
    args=ap.parse_args()

    random.seed(args.seed)
    rows=list(iter_jsonl(Path(args.inp)))
    random.shuffle(rows)
    sample = rows[:args.max]

    taxonomy_version = 'v1.0-draft'
    out_rows=[]
    for i,r in enumerate(sample):
        text = r.get('text') or r.get('text') or r.get('text')
        if not text: continue
        rec = dict(ANNOTATION_SCHEMA)
        rec.update({
            'id': i,
            'text': text,
            'sourceUrl': r.get('sourceUrl'),
            'candidateType': classify_candidate_type(text),
            'qualityScore': score_quality(text),
            'sample_phase': 'seed',
            'taxonomyVersion': taxonomy_version
        })
        out_rows.append(rec)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open('w', encoding='utf-8') as w:
        for rec in out_rows:
            w.write(json.dumps(rec, ensure_ascii=False) + '\n')
    meta={
        'timestamp': datetime.utcnow().isoformat()+'Z',
        'input': str(Path(args.inp).resolve()),
        'output': str(out_path.resolve()),
        'count': len(out_rows),
        'seed': args.seed,
        'taxonomyVersion': taxonomy_version
    }
    print(json.dumps(meta, indent=2))

if __name__ == '__main__':
    main()
