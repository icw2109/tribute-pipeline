import json, tempfile, os
from insights.heuristic import heuristic_classify
from insights.ensemble import EnsembleClassifier

# Lightweight synthetic self-train artifacts creation helper
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
import joblib

SAMPLES = [
    ("Slashing risk if validators go offline", "Risk"),
    ("Throughput improved to 5k TPS", "Advantage"),
    ("Users can delegate stake via the protocol", "Advantage"),
    ("Token unlock schedule increases supply", "Risk"),
    ("Architecture uses modular consensus", "Neutral"),
]


def _make_model(tmpdir: str):
    texts, labels = zip(*SAMPLES)
    vec = TfidfVectorizer().fit(texts)
    X = vec.transform(texts)
    clf = LogisticRegression(max_iter=200).fit(X, labels)
    joblib.dump(clf, os.path.join(tmpdir,'model.pkl'))
    joblib.dump(vec, os.path.join(tmpdir,'vectorizer.pkl'))
    with open(os.path.join(tmpdir,'metadata.json'),'w',encoding='utf-8') as w:
        json.dump({"labelSet":["Risk","Advantage","Neutral"],"taxonomyVersion":"adin.v2"}, w)
    return tmpdir


def test_heuristic_outputs():
    res = heuristic_classify("Slashing leads to penalties")
    assert res['label'] == 'Risk'
    assert res['ruleStrength'] >= 0.9


def test_ensemble_with_self_train():
    with tempfile.TemporaryDirectory() as d:
        _make_model(d)
        ens = EnsembleClassifier(self_train_model_path=d, config={'ruleStrongThreshold':0.95,'modelFloor':0.8})
        out = ens.classify("Throughput improved to 5k TPS")
        assert out['label'] in {'Advantage','Risk','Neutral'}
        assert 'modelProbs' in out

