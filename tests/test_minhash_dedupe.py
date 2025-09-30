from insights.pipeline import minhash_dedupe, InsightCandidate

def test_minhash_dedupe_basic():
    base = "Protocol enables efficient staking rewards for users with high performance."
    # create near duplicates with small edits
    items = [
        InsightCandidate(source_url=f'u{i}', section='s', text=base.replace('high', word), evidence=['e'])
        for i, word in enumerate(['high','higher','highly','high'])
    ]
    out = minhash_dedupe(items)
    assert len(out) < len(items)
