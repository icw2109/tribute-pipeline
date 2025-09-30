from insights.tag_inference import infer_with_validation


def case(text):
    inf = infer_with_validation(text)
    return inf.label, inf.tag


def test_risk_precedence_over_advantage():
    lbl, tag = case("Strong adoption numbers but facing regulatory uncertainty in US")
    assert lbl == 'Risk'
    assert tag == 'Regulatory'


def test_advantage_traction():
    lbl, tag = case("User adoption and TVL growth accelerated this quarter")
    assert lbl == 'Advantage'
    assert tag == 'Traction'


def test_advantage_partners():
    lbl, tag = case("New integration partnership with major exchange announced")
    assert lbl == 'Advantage'
    assert tag == 'Partners'


def test_neutral_architecture():
    lbl, tag = case("The architecture includes a coordination layer and execution module")
    assert lbl == 'Neutral'
    assert tag == 'Architecture'


def test_fallback_mechanics():
    lbl, tag = case("This system uses tokens for participation")
    assert lbl == 'Neutral'
    assert tag == 'Mechanics'


def test_token_supply_risk():
    lbl, tag = case("Upcoming large token unlock could introduce dilution")
    assert lbl == 'Risk'
    assert tag == 'Token Supply'


def test_security_slash_risk():
    lbl, tag = case("Minor bug and potential exploit reported in slashing module")
    assert lbl == 'Risk'
    assert tag == 'Security/Slash'
