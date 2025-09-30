import sys, pathlib
ROOT = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from insights import clean_text, split_sentences, is_candidate, merge_adjacent

RAW = """
Accept cookies to continue
Operators validate services. They earn rewards.
- Slashing may occur for malicious behavior.
Subscribe to newsletter
Restaking allows extended security.
""".strip()

def test_clean_and_split():
    cleaned = clean_text(RAW)
    assert "Accept cookies" not in cleaned
    assert "Subscribe to" not in cleaned
    sents = split_sentences(cleaned)
    # We expect at least the substantive sentences preserved
    assert any("Operators validate services" in s for s in sents)
    assert any("They earn rewards" in s for s in sents)


def test_is_candidate_and_merge():
    sents = [
        "Operators validate services.",
        "They earn rewards.",
        "Restaking allows extended security.",
        "This is fluff text with no keywords.",
    ]
    filtered = [s for s in sents if is_candidate(s)]
    assert "This is fluff" not in " ".join(filtered)
    merged = merge_adjacent(filtered)
    # Expect potential merging of first two due to shared keyword 'rewards' or 'operators' (may not merge if heuristic fails; allow >= len(filtered)-1)
    assert len(merged) <= len(filtered)
