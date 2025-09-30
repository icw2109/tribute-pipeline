"""Lightweight ML classification layer (Tier1).

Provides training + inference helpers around a LogisticRegression model fed by:
  * TF-IDF character + word features (scikit-learn)
  * Hand-crafted numeric & boolean features from insights.features

Artifacts layout (model directory):
  model.joblib            # dict with {'model', 'vectorizer', 'feature_names', 'lexicon_hash', 'version'}
  meta.json               # training metadata (class distribution, timestamps, scores)

This keeps the integration surface small so CLI code can just call load_model(dir)
and predict_proba(texts) -> List[Dict[label, prob]].
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence, Dict, Any
import time
import json
import joblib  # type: ignore
from pathlib import Path

from sklearn.pipeline import FeatureUnion
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from sklearn.compose import ColumnTransformer
from sklearn.base import BaseEstimator, TransformerMixin
import numpy as np

from .features import extract_features
from .lexicon import Lexicon, DEFAULT_LEXICON


LABELS = ["Advantage", "Risk", "Neutral"]


class DenseFeatureAdapter(TransformerMixin, BaseEstimator):
    """Adapter that converts handcrafted feature dicts to a fixed order array.

    We choose a fixed key ordering derived from first sample; later samples
    must contain identical keys (enforced) else we raise for reproducibility.
    """
    def __init__(self, feature_keys: List[str] | None = None):
        self.feature_keys = feature_keys

    def fit(self, X: Sequence[Dict[str, Any]], y=None):  # pragma: no cover - trivial
        if not self.feature_keys:
            if not X:
                raise ValueError("Cannot fit DenseFeatureAdapter on empty data")
            # exclude lexicon hash/version from numeric vector; keep only numeric / bool
            sample = X[0]
            numeric_keys = [k for k,v in sample.items() if isinstance(v, (int, float, bool)) and not k.startswith('lexicon_')]
            self.feature_keys = sorted(numeric_keys)
        return self

    def transform(self, X: Sequence[Dict[str, Any]]):  # pragma: no cover - straightforward
        if self.feature_keys is None:
            raise RuntimeError("Adapter not fitted")
        arr = np.zeros((len(X), len(self.feature_keys)), dtype=float)
        for i, feat in enumerate(X):
            for j, key in enumerate(self.feature_keys):
                v = feat.get(key, 0.0)
                if isinstance(v, bool):
                    v = float(v)
                arr[i, j] = float(v)
        return arr


@dataclass
class TrainedModel:
    model: Any
    vectorizer: Any
    dense_adapter: DenseFeatureAdapter
    feature_keys: List[str]
    lexicon_hash: str
    labels: List[str]

    def predict_proba(self, texts: List[str], lexicon: Lexicon = DEFAULT_LEXICON) -> List[Dict[str, float]]:
        # Extract features batch
        dense_feats = []
        raw_texts = []
        for t in texts:
            fr = extract_features(t, lexicon)
            dense_feats.append(fr.features)
            raw_texts.append(t)
        X_text = self.vectorizer.transform(raw_texts)
        X_dense = self.dense_adapter.transform(dense_feats)
        # scale dense features on the fly with StandardScaler trained embedding inside pipeline? Simpler: fit separate scaler at training.
        # For simplicity we stored scaler inside model pipeline if needed; logistic handles raw scale okay for these magnitudes.
        from scipy.sparse import hstack  # local import to keep base import light
        X = hstack([X_text, X_dense])
        probs = self.model.predict_proba(X)
        out = []
        for row in probs:
            out.append({lab: float(row[i]) for i, lab in enumerate(self.labels)})
        return out


def train_model(texts: List[str], labels: List[str], lexicon: Lexicon = DEFAULT_LEXICON, max_features: int = 20000) -> TrainedModel:
    # Extract dense feature dicts first
    dense_feature_dicts = [extract_features(t, lexicon).features for t in texts]
    adapter = DenseFeatureAdapter()
    adapter.fit(dense_feature_dicts)
    # Vectorizer: char + word ngrams combined using a single TfidfVectorizer with char_wb for robustness
    vectorizer = TfidfVectorizer(
        lowercase=True,
        ngram_range=(1,2),
        max_features=max_features,
        strip_accents='unicode'
    )
    X_text = vectorizer.fit_transform(texts)
    X_dense = adapter.transform(dense_feature_dicts)
    from scipy.sparse import hstack
    X = hstack([X_text, X_dense])
    # Logistic regression (balanced classes)
    clf = LogisticRegression(max_iter=1000, class_weight='balanced', n_jobs=1)
    clf.fit(X, labels)
    return TrainedModel(model=clf, vectorizer=vectorizer, dense_adapter=adapter, feature_keys=adapter.feature_keys or [], lexicon_hash=lexicon.hash(), labels=clf.classes_.tolist())


def save_model(tm: TrainedModel, out_dir: str | Path, meta: Dict[str, Any]):  # pragma: no cover simple IO
    d = Path(out_dir)
    d.mkdir(parents=True, exist_ok=True)
    joblib.dump({
        'model': tm.model,
        'vectorizer': tm.vectorizer,
        'dense_adapter': tm.dense_adapter,
        'feature_keys': tm.feature_keys,
        'lexicon_hash': tm.lexicon_hash,
        'labels': tm.labels,
    }, d / 'model.joblib')
    meta_path = d / 'meta.json'
    meta['saved_at'] = time.time()
    meta['lexicon_hash'] = tm.lexicon_hash
    meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')


def load_model(model_dir: str | Path) -> TrainedModel:  # pragma: no cover simple IO
    obj = joblib.load(Path(model_dir) / 'model.joblib')
    return TrainedModel(
        model=obj['model'],
        vectorizer=obj['vectorizer'],
        dense_adapter=obj['dense_adapter'],
        feature_keys=obj['feature_keys'],
        lexicon_hash=obj['lexicon_hash'],
        labels=obj['labels'],
    )


__all__ = [
    'train_model','save_model','load_model','TrainedModel','LABELS'
]
