import pytest

from insights.backends import train_backend, load_backend, LABELS
from insights.lexicon import DEFAULT_LEXICON

SYN_DATA = [
    ("security vulnerability may cause loss", "Risk"),
    ("strong adoption and growth", "Advantage"),
    ("operational update released", "Neutral")
]

@pytest.mark.skipif('transformers' not in __import__('sys').modules and True, reason='transformers not installed in test environment')
def test_distilbert_backend_train_predict(tmp_path):
    # Only run if transformers import succeeds
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
    except Exception:
        pytest.skip('transformers/torch not available')
    texts = [t for t,_ in SYN_DATA]
    labels = [l for _,l in SYN_DATA]
    backend = train_backend('distilbert', texts, labels, DEFAULT_LEXICON, hf_model='distilbert-base-uncased', embed_batch_size=2, max_seq_len=64)
    probs = backend.predict_proba(texts)
    assert len(probs) == len(texts)
    for row in probs:
        assert set(row.keys()) == set(backend.labels)
        s = sum(row.values())
        assert 0.99 <= s <= 1.01
    # save/load
    meta = {'test': True}
    backend.save(tmp_path, meta)
    loaded = load_backend(tmp_path)
    lprobs = loaded.predict_proba([texts[0]])[0]
    assert set(lprobs.keys()) == set(backend.labels)
