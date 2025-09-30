from insights.metrics import extract_metrics


def surfaces(kinds, metrics):
    return [m.surface for m in metrics if m.kind in kinds]


def test_percent_and_year_and_currency():
    text = "Revenue grew 12.5% in 2024 reaching $50M while costs stayed at $1.2B and legacy remained 500k USD."
    ms = extract_metrics(text)
    kinds = [m.kind for m in ms]
    # Expect at least one percent, one year, and currency items
    assert 'percent' in kinds
    assert 'year' in kinds
    assert any(m.kind == 'currency' for m in ms)
    # Check value scaling
    money = {m.surface: m.value for m in ms if m.kind == 'currency'}
    # $50M -> 50e6, $1.2B -> 1.2e9, 500k USD -> 500e3
    assert any(abs(v - 50_000_000) < 1e-6 for v in money.values())
    assert any(abs(v - 1_200_000_000) < 1e-3 for v in money.values())
    assert any(abs(v - 500_000) < 1e-3 for v in money.values())


def test_plain_number_not_year():
    text = "We processed 987 transactions."  # 987 not a year pattern (still generic number)
    ms = extract_metrics(text)
    assert any(m.kind == 'number' and m.value == 987 for m in ms)

