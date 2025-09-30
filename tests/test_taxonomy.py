from insights.adin_taxonomy import (
    TAXONOMY_VERSION,
    TopLevel,
    ADVANTAGE_TAGS,
    RISK_TAGS,
    NEUTRAL_TAGS,
    ALL_TAGS,
    validate,
    taxonomy_summary,
)


def test_taxonomy_version_present():
    assert TAXONOMY_VERSION.startswith("adin.v" )


def test_all_tags_partition():
    # Disjoint sets
    assert ADVANTAGE_TAGS.isdisjoint(RISK_TAGS)
    assert ADVANTAGE_TAGS.isdisjoint(NEUTRAL_TAGS)
    assert RISK_TAGS.isdisjoint(NEUTRAL_TAGS)
    # Union completeness
    assert ALL_TAGS == ADVANTAGE_TAGS | RISK_TAGS | NEUTRAL_TAGS


def test_validate_expected_pairs():
    for t in ADVANTAGE_TAGS:
        assert validate(TopLevel.Advantage.value, t)
    for t in RISK_TAGS:
        assert validate(TopLevel.Risk.value, t)
    for t in NEUTRAL_TAGS:
        assert validate(TopLevel.Neutral.value, t)


def test_validate_reject_mismatch():
    # pick one advantage tag and ensure can't pair with Risk
    sample_adv = next(iter(ADVANTAGE_TAGS))
    assert not validate(TopLevel.Risk.value, sample_adv)


def test_taxonomy_summary_structure():
    summ = taxonomy_summary()
    assert summ['version'] == TAXONOMY_VERSION
    assert set(summ['all']) == ALL_TAGS
    assert set(summ['advantage']) == ADVANTAGE_TAGS
    assert set(summ['risk']) == RISK_TAGS
    assert set(summ['neutral']) == NEUTRAL_TAGS
