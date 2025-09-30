import argparse, json, importlib, sys, os

# Ensure parent directory (containing package 'insights') is on sys.path ahead of this script's directory
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

try:
    extract_insights = importlib.import_module('insights').extract_insights  # type: ignore[attr-defined]
except Exception as e:
    sys.stderr.write(f"Failed to import insights package: {e}\n")
    raise

def build_parser():
    p = argparse.ArgumentParser(description="Phase 2: Extract raw atomic insights (no classification) from scraped pages.")
    p.add_argument("--pages", required=True, help="Path to scraped_pages.jsonl produced by scrape phase")
    p.add_argument("--out", required=True, help="Path to write insights_raw.jsonl")
    p.add_argument("--maxInsights", type=int, default=100, help="Maximum insights to emit (cap)")
    p.add_argument("--minInsights", type=int, default=50, help="Advisory lower bound (not strictly enforced)")
    p.add_argument("--minLen", type=int, default=25, help="Minimum text length to keep (post-extraction)")
    p.add_argument("--fuzzyDedupe", action="store_true", help="Apply Jaccard-based near-duplicate collapsing (>=0.9)")
    p.add_argument("--minhashFuzzy", action="store_true", help="Use MinHash-based large-scale near-duplicate detection")
    p.add_argument("--statsOut", help="Path to write stats JSON (sidecar)")
    p.add_argument("--baselineNeutralLen", type=int, help="Override baseline neutral inclusion min length (default 40)")
    p.add_argument("--sectionHeuristic", choices=["path","none"], default="path", help="Section derivation strategy (default path)")
    return p

def main(argv=None):
    args = build_parser().parse_args(argv)
    stats = extract_insights(
        scraped_path=args.pages,
        out_path=args.out,
        target_count=(args.minInsights, args.maxInsights),
        do_classify=False,
        do_metrics=False,
        do_fuzzy=args.fuzzyDedupe,
        do_minhash=args.minhashFuzzy,
        compute_confidence=False,
        min_len=args.minLen,
        baseline_neutral_len=args.baselineNeutralLen,
        section_heuristic=args.sectionHeuristic,
    )
    # Sidecar stats
    if args.statsOut:
        with open(args.statsOut, 'w', encoding='utf-8') as f:
            json.dump(stats, f, indent=2)

if __name__ == "__main__":
    main()
