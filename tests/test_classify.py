from insights.classify import classify


def test_risk_precedence_over_advantage():
    text = "Strong growth but faces security risk and potential exploit exposure"
    res = classify(text)
    assert res.label == 'Risk'
    assert 'risk' in res.signals


def test_advantage_when_positive_terms():
    text = "Protocol shows scalable growth and increased adoption in Q1"
    res = classify(text)
    assert res.label == 'Advantage'
    assert 'growth' in res.signals or 'adoption' in res.signals


def test_neutral_when_no_signals():
    text = "The committee met to discuss routine scheduling matters"
    res = classify(text)
    assert res.label == 'Neutral'


def test_negated_risk_removed():
    text = "No security risk was identified during the audited review"
    res = classify(text)
    # 'risk' appears but negated; should not classify as Risk; may become Advantage due to 'audited'? stays Neutral
    assert res.label != 'Risk'
