import tempfile, json, os, math
from pathlib import Path

from insights.backends import train_backend, load_backend, LABELS
from insights.lexicon import DEFAULT_LEXICON

SYN_DATA = [
    ("protocol adds more validators and increases security", "Advantage"),
    ("critical vulnerability leads to potential loss", "Risk"),
    ("team announces roadmap for scaling", "Advantage"),
    ("regulatory uncertainty could hinder adoption", "Risk"),
    ("the network operates with stable performance", "Neutral"),
    ("no major updates were released", "Neutral")
]


def _train_and_assert(backend_name: str):
    texts = [t for t,_ in SYN_DATA]
    labels = [l for _,l in SYN_DATA]
    backend = train_backend(backend_name, texts, labels, DEFAULT_LEXICON, max_features=500 if backend_name=='tfidf' else None, n_features=2**10 if backend_name=='hashing' else None)
    probs = backend.predict_proba(texts)
    assert len(probs) == len(texts)
    for row in probs:
        # labels ordering consistency
        assert list(row.keys()) == backend.labels
        s = sum(row.values())
        assert 0.99 <= s <= 1.01, f"probabilities should sum to 1, got {s}"  # allow minor fp error
    # save/load round trip
    with tempfile.TemporaryDirectory() as d:
        meta = {"test": True}
        backend.save(d, meta)
        loaded = load_backend(d)
        lprobs = loaded.predict_proba([texts[0]])[0]
        assert set(lprobs.keys()) == set(backend.labels)


def test_tfidf_backend():
    _train_and_assert('tfidf')


def test_hashing_backend():
    _train_and_assert('hashing')
