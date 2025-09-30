from insights.features import extract_features
from insights.lexicon import DEFAULT_LEXICON


def test_advantage_launch_with_numeric():
    txt = "We launched v2 delivering 10x throughput for users."
    fr = extract_features(txt, DEFAULT_LEXICON)
    assert fr.features["adv_count"] >= 1
    assert fr.features["has_numeric"] is True
    # Should capture ratio pattern
    assert fr.features["ratio_count"] == 1
    # Ensure launch-related token captured somewhere (order not guaranteed)
    assert any(t.startswith("launch") or t.startswith("launched") for t in fr.trace["advantage_terms"])


def test_negated_risk():
    txt = "No security risk was identified."
    fr = extract_features(txt)
    # risk term present but negated
    assert fr.features["risk_count"] >= 1
    assert fr.features["negated_risk"] is True


def test_slashing_risk_cluster():
    txt = "Slashing penalties may reduce rewards."
    fr = extract_features(txt)
    assert fr.features["risk_count"] >= 1
    assert "slashing" in fr.trace["risk_terms"] or "penalties" in fr.trace["risk_terms"]


def test_negated_advantage():
    txt = "Not yet launched, still in testing."
    fr = extract_features(txt)
    assert fr.features["adv_count"] >= 1  # 'launch' token appears
    assert fr.features["negated_advantage"] is True
