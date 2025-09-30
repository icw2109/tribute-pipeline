import argparse, json, re, sys, statistics
from pathlib import Path

RE_YEAR = re.compile(r"\b(19|20|21)\d{2}\b")
RE_PERCENT = re.compile(r"\b\d{1,3}(?:\.\d+)?%\b")

SCHEMA_FIELDS = {"url", "title", "text", "depth", "discoveredFrom"}

def analyze(path: Path, limit: int | None = None):
    counts = 0
    missing_schema = 0
    empty_text = 0
    total_chars = 0
    depths = []
    years = 0
    percents = 0
    sample_errors = []
    with path.open('r', encoding='utf-8') as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError as e:
                sample_errors.append((line_no, str(e)))
                continue
            counts += 1
            if not SCHEMA_FIELDS.issubset(obj.keys()):
                missing_schema += 1
            text = obj.get('text', '') or ''
            if not text.strip():
                empty_text += 1
            total_chars += len(text)
            depths.append(obj.get('depth', -1))
            years += len(RE_YEAR.findall(text))
            percents += len(RE_PERCENT.findall(text))
            if limit and counts >= limit:
                break
    avg_chars = (total_chars / counts) if counts else 0
    depth_stats = {
        'min': min(depths) if depths else None,
        'max': max(depths) if depths else None,
        'mean': statistics.mean(depths) if depths else None,
    }
    return {
        'records': counts,
        'missing_schema': missing_schema,
        'empty_text': empty_text,
        'avg_text_chars': round(avg_chars, 2),
        'depth': depth_stats,
        'year_tokens': years,
        'percent_tokens': percents,
        'decode_errors': sample_errors[:5],
    }

def build_parser():
    p = argparse.ArgumentParser(description='Validate a scraped JSONL crawl file for schema + simple quality heuristics.')
    p.add_argument('input', help='Path to crawl JSONL file')
    p.add_argument('--limit', type=int, help='Only analyze first N records')
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    report = analyze(Path(args.input), args.limit)
    print(json.dumps(report, indent=2))

if __name__ == '__main__':  # pragma: no cover
    main()
