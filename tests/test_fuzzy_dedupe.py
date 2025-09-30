from insights.pipeline import fuzzy_dedupe, InsightCandidate

def test_fuzzy_dedupe_removes_near_duplicate():
    a = InsightCandidate(source_url='u1', section='s', text='Protocol enables efficient staking rewards for users.', evidence=['x'])
    b = InsightCandidate(source_url='u2', section='s', text='Protocol enables efficient staking reward for user', evidence=['y'])
    c = InsightCandidate(source_url='u3', section='s', text='Completely different sentence about risk.', evidence=['z'])
    out = fuzzy_dedupe([a,b,c], threshold=0.85)
    texts = [o.text for o in out]
    # Expect only one of a/b remains plus c (length 2)
    assert len(out) == 2
    assert any('Completely different' in t for t in texts)

def test_fuzzy_dedupe_keeps_distinct():
    a = InsightCandidate(source_url='u1', section='s', text='Staking rewards increase adoption.', evidence=['x'])
    b = InsightCandidate(source_url='u2', section='s', text='Risk management improves security posture.', evidence=['y'])
    out = fuzzy_dedupe([a,b], threshold=0.9)
    assert len(out) == 2
