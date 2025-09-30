from insights.metrics import extract_metrics

def test_date_fragments_not_split():
    text = "Release dates 09-18 and 09-16 appeared with version 3.13.7 and 3.14% growth."  # 3.14% should count percent; version numbers shouldn't become currency
    ms = extract_metrics(text)
    surfaces = [m.surface for m in ms]
    # Ensure date fragments like 09, 18 not present
    assert not any(s in {"09","18","16"} for s in surfaces)
    # 3.14% captured as percent
    assert any(s.endswith('%') for s in surfaces)

