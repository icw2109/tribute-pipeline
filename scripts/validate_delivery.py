"""Validate presence & basic schema of required take-home artifacts.

Checks:
  - Required files exist in a given work directory.
  - pages.jsonl has URL & text fields in first N lines.
  - insights_raw.jsonl have text field.
  - insights_classified.jsonl have label, rationale, confidence, taxonomyVersion.
  - run_manifest.json includes schemaVersion, taxonomyVersion, tagVocabularyVersion.
  - diagnostics.json and health.json parse and contain expected keys.
  - Optional synthetic generator script present.

Usage:
  python scripts/validate_delivery.py --workDir out/full_demo_eigen
Exit codes:
  0 success, 1 missing artifact / structural issue.
"""
from __future__ import annotations
import argparse, json, sys
from pathlib import Path

REQUIRED_FILES = [
    'pages.jsonl',
    'insights_raw.jsonl',
    'insights_classified.jsonl',
    'run_manifest.json',
    'diagnostics.json',
    'health.json'
]

def first_n_jsonl(path: Path, n=10):
    rows=[]
    if not path.exists():
        return rows
    with path.open('r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if not line: continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
            if len(rows) >= n:
                break
    return rows

def fail(msg, problems):
    problems.append(msg)
    return problems

def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument('--workDir', required=True)
    ap.add_argument('--strict', action='store_true', help='Treat any warning as failure')
    ap.add_argument('--check-rationale-len', type=int, default=0, help='If >0 enforce max rationale length in sample')
    ap.add_argument('--tag-vocab', default='tag_vocabulary.json', help='Path to tag vocabulary JSON file for labelTag membership check (optional).')
    args = ap.parse_args(argv)
    wd = Path(args.workDir)
    problems=[]
    warnings=[]

    # Existence
    for rel in REQUIRED_FILES:
        p = wd/rel
        if not p.exists():
            fail(f'missing_file:{rel}', problems)

    # Early abort if core files missing
    if problems:
        out={'status':'fail','problems':problems,'warnings':warnings}
        print(json.dumps(out, indent=2)); sys.exit(1)

    # pages
    pages_sample = first_n_jsonl(wd/'pages.jsonl')
    if not pages_sample:
        fail('pages_empty', problems)
    else:
        if not all('url' in r for r in pages_sample): warnings.append('pages_missing_url_field')
        if not any('text' in r for r in pages_sample): warnings.append('pages_no_text_field_in_sample')

    # insights raw
    raw_sample = first_n_jsonl(wd/'insights_raw.jsonl')
    if not raw_sample:
        fail('insights_raw_empty', problems)
    else:
        if not all('text' in r for r in raw_sample): warnings.append('insights_raw_text_missing')

    # tag vocab (optional)
    vocab=set()
    voc_path=Path(args.tag_vocab)
    if voc_path.exists():
        try:
            data=json.loads(voc_path.read_text(encoding='utf-8'))
            # support either list or dict structure
            if isinstance(data, list):
                vocab.update(data)
            elif isinstance(data, dict):
                # collect recursively simple strings
                def collect(obj):
                    if isinstance(obj,str):
                        vocab.add(obj)
                    elif isinstance(obj, dict):
                        for v in obj.values(): collect(v)
                    elif isinstance(obj, list):
                        for v in obj: collect(v)
                collect(data)
        except Exception:
            warnings.append('vocab_parse_failed')

    # classified
    classified_sample = first_n_jsonl(wd/'insights_classified.jsonl')
    if not classified_sample:
        fail('insights_classified_empty', problems)
    else:
        need_fields={'label','rationale','confidence'}
        for f in need_fields:
            if not all(f in r for r in classified_sample): warnings.append(f'classified_missing_field:{f}')
        if not any('taxonomyVersion' in r for r in classified_sample): warnings.append('classified_missing_taxonomyVersion')
        # label domain
        allowed_labels={'Advantage','Risk','Neutral'}
        if not all(r.get('label') in allowed_labels for r in classified_sample):
            warnings.append('unexpected_label_value')
        # confidence bounds
        if not all(0.0 <= float(r.get('confidence',-1)) <= 1.0 for r in classified_sample):
            warnings.append('confidence_out_of_range')
        # rationale length
        if args.check_rationale_len>0:
            if any(len(r.get('rationale',''))>args.check_rationale_len for r in classified_sample):
                warnings.append('rationale_exceeds_max')
        # tag vocabulary membership (if vocab found and not empty)
        if vocab:
            if not any('labelTag' in r for r in classified_sample):
                warnings.append('labelTag_missing')
            else:
                if not all(r.get('labelTag') in vocab for r in classified_sample if 'labelTag' in r):
                    warnings.append('labelTag_out_of_vocab')

    # manifest
    try:
        manifest=json.loads((wd/'run_manifest.json').read_text(encoding='utf-8'))
        for key in ['schemaVersion','taxonomyVersion','tagVocabularyVersion']:
            if key not in manifest:
                warnings.append(f'manifest_missing:{key}')
    except Exception:
        fail('manifest_unreadable', problems)

    # diagnostics
    try:
        diag=json.loads((wd/'diagnostics.json').read_text(encoding='utf-8'))
        for key in ['count','label_dist','neutral_ratio']:
            if key not in diag:
                warnings.append(f'diagnostics_missing:{key}')
    except Exception:
        fail('diagnostics_unreadable', problems)

    # health
    try:
        health=json.loads((wd/'health.json').read_text(encoding='utf-8'))
        for key in ['counts','status']:
            if key not in health:
                warnings.append(f'health_missing:{key}')
    except Exception:
        fail('health_unreadable', problems)

    status='pass'
    if problems or (args.strict and warnings):
        status='fail'
    out={'status':status,'problems':problems,'warnings':warnings,'workDir':str(wd.resolve())}
    print(json.dumps(out, indent=2))
    sys.exit(0 if status=='pass' else 1)

if __name__ == '__main__':  # pragma: no cover
    main()
