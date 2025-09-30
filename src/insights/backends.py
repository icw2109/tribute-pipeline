"""Modular model backends for classification.

Provides a thin abstraction so we can plug different lightweight models
without rewriting CLI integration logic. Two initial backends:

  * TfidfLogRegBackend  - classic TF-IDF word/bi-word ngrams + handcrafted dense features
  * HashingLogRegBackend - hashing trick + tf-idf transform + dense features (smaller disk, constant memory)

All backends expose:
  - labels: ordered list of label names
  - lexicon_hash: reproducibility token (must match runtime lexicon)
  - predict_proba(texts, lexicon)
  - save(out_dir, meta)

Disk layout (backends share the same top-level file names):
  model.joblib  # serialized dict (includes key 'backend')
  meta.json     # training metadata (includes backend name + scores)

Backward compatibility: legacy artifacts produced by ml.train_model (without
'backend' key) can still be loaded via load_legacy_adapter().
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Dict, Any, Sequence
import time, json

import joblib  # type: ignore
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.feature_extraction.text import TfidfVectorizer, HashingVectorizer
from sklearn.feature_extraction.text import TfidfTransformer

from .features import extract_features
from .lexicon import Lexicon, DEFAULT_LEXICON

LABELS = ["Advantage", "Risk", "Neutral"]


class ModelBackend:
    backend_name: str = "abstract"

    def predict_proba(self, texts: List[str], lexicon: Lexicon = DEFAULT_LEXICON) -> List[Dict[str, float]]:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def labels(self) -> List[str]:  # pragma: no cover - interface
        raise NotImplementedError

    @property
    def lexicon_hash(self) -> str:  # pragma: no cover - interface
        raise NotImplementedError

    def save(self, out_dir: str | Path, meta: Dict[str, Any]):  # pragma: no cover - interface
        raise NotImplementedError


class DenseFeatureAdapter:
    """Converts handcrafted feature dicts to fixed-order numpy array.

    Re-implemented here (duplicated from ml.py) to decouple from legacy path.
    """
    def __init__(self, feature_keys: List[str] | None = None):
        self.feature_keys = feature_keys

    def fit(self, X: Sequence[Dict[str, Any]]):  # pragma: no cover trivial
        if not self.feature_keys:
            if not X:
                raise ValueError("Cannot fit DenseFeatureAdapter on empty data")
            sample = X[0]
            numeric_keys = [k for k,v in sample.items() if isinstance(v, (int, float, bool)) and not k.startswith('lexicon_')]
            self.feature_keys = sorted(numeric_keys)
        return self

    def transform(self, X: Sequence[Dict[str, Any]]):  # pragma: no cover straightforward
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


class TfidfLogRegBackend(ModelBackend):
    backend_name = "tfidf"

    def __init__(self, model, vectorizer, dense_adapter: DenseFeatureAdapter, feature_keys: List[str], lexicon_hash: str, labels: List[str]):
        self._model = model
        self._vectorizer = vectorizer
        self._dense_adapter = dense_adapter
        self._feature_keys = feature_keys
        self._lexicon_hash = lexicon_hash
        self._labels = labels

    @property
    def labels(self):
        return self._labels

    @property
    def lexicon_hash(self):
        return self._lexicon_hash

    def predict_proba(self, texts: List[str], lexicon: Lexicon = DEFAULT_LEXICON):
        dense_dicts = [extract_features(t, lexicon).features for t in texts]
        X_text = self._vectorizer.transform(texts)
        X_dense = self._dense_adapter.transform(dense_dicts)
        from scipy.sparse import hstack  # local import
        X = hstack([X_text, X_dense])
        probs = self._model.predict_proba(X)
        out: List[Dict[str, float]] = []
        for row in probs:
            out.append({lab: float(row[i]) for i, lab in enumerate(self._labels)})
        return out

    def save(self, out_dir: str | Path, meta: Dict[str, Any]):  # pragma: no cover IO
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            'backend': self.backend_name,
            'model': self._model,
            'vectorizer': self._vectorizer,
            'dense_adapter': self._dense_adapter,
            'feature_keys': self._feature_keys,
            'lexicon_hash': self._lexicon_hash,
            'labels': self._labels,
        }, d / 'model.joblib')
        meta_path = d / 'meta.json'
        meta['saved_at'] = time.time()
        meta['lexicon_hash'] = self._lexicon_hash
        meta['backend'] = self.backend_name
        meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')


class HashingLogRegBackend(ModelBackend):
    backend_name = "hashing"

    def __init__(self, model, dense_adapter: DenseFeatureAdapter, feature_keys: List[str], lexicon_hash: str, labels: List[str], *, n_features: int, ngram_range=(1,2), alternate_sign: bool = True):
        self._model = model
        self._dense_adapter = dense_adapter
        self._feature_keys = feature_keys
        self._lexicon_hash = lexicon_hash
        self._labels = labels
        self._n_features = n_features
        self._ngram_range = ngram_range
        self._alternate_sign = alternate_sign
        # Stateless components
        self._hash = HashingVectorizer(n_features=n_features, alternate_sign=alternate_sign, ngram_range=ngram_range, lowercase=True, strip_accents='unicode')
        self._tfidf = TfidfTransformer()  # fitted during training (stores idf)

    @property
    def labels(self):
        return self._labels

    @property
    def lexicon_hash(self):
        return self._lexicon_hash

    def predict_proba(self, texts: List[str], lexicon: Lexicon = DEFAULT_LEXICON):
        dense_dicts = [extract_features(t, lexicon).features for t in texts]
        X_h = self._hash.transform(texts)
        X_text = self._tfidf.transform(X_h)
        X_dense = self._dense_adapter.transform(dense_dicts)
        from scipy.sparse import hstack
        X = hstack([X_text, X_dense])
        probs = self._model.predict_proba(X)
        out: List[Dict[str, float]] = []
        for row in probs:
            out.append({lab: float(row[i]) for i, lab in enumerate(self._labels)})
        return out

    def save(self, out_dir: str | Path, meta: Dict[str, Any]):  # pragma: no cover IO
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            'backend': self.backend_name,
            'model': self._model,
            'dense_adapter': self._dense_adapter,
            'feature_keys': self._feature_keys,
            'lexicon_hash': self._lexicon_hash,
            'labels': self._labels,
            'n_features': self._n_features,
            'ngram_range': self._ngram_range,
            'alternate_sign': self._alternate_sign,
            'tfidf_idf': getattr(self._tfidf, 'idf_', None),
        }, d / 'model.joblib')
        meta_path = d / 'meta.json'
        meta['saved_at'] = time.time()
        meta['lexicon_hash'] = self._lexicon_hash
        meta['backend'] = self.backend_name
        meta['n_features'] = self._n_features
        meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')


def _fit_dense_adapter(texts: List[str], lexicon: Lexicon) -> tuple[DenseFeatureAdapter, List[Dict[str, Any]]]:
    dense_dicts = [extract_features(t, lexicon).features for t in texts]
    adapter = DenseFeatureAdapter()
    adapter.fit(dense_dicts)
    return adapter, dense_dicts


def _augment_with_metadata(texts: List[str]) -> List[str]:
    """Optional metadata prefix injection.

    If a training text contains a JSON encoded metadata prefix line like
    META::{"candidateType":"metric","qualityScore":0.87}\nActual text...
    we convert it to token prefixes: __TYPE_metric __Q_hi  followed by the text.
    This lets classical models exploit candidateType / quality without schema changes.
    If no such pattern, text returned unchanged.
    """
    out: List[str] = []
    import json as _json
    for t in texts:
        if t.startswith('META::'):
            try:
                first_nl = t.find('\n')
                hdr = t[6:first_nl] if first_nl != -1 else t[6:]
                meta = _json.loads(hdr)
                body = t[first_nl+1:] if first_nl != -1 else ''
                ctype = meta.get('candidateType','other')
                q = meta.get('qualityScore',0.0)
                if q >= 0.75: qb = 'hi'
                elif q >= 0.5: qb = 'mid'
                else: qb = 'lo'
                prefix = f"__TYPE_{ctype} __Q_{qb} "
                out.append(prefix + body)
                continue
            except Exception:
                pass
        out.append(t)
    return out

def train_tfidf_backend(texts: List[str], labels: List[str], lexicon: Lexicon = DEFAULT_LEXICON, *, max_features: int = 20000) -> TfidfLogRegBackend:
    texts = _augment_with_metadata(texts)
    adapter, dense_dicts = _fit_dense_adapter(texts, lexicon)
    vectorizer = TfidfVectorizer(lowercase=True, ngram_range=(1,2), max_features=max_features, strip_accents='unicode')
    X_text = vectorizer.fit_transform(texts)
    X_dense = adapter.transform(dense_dicts)
    from scipy.sparse import hstack
    X = hstack([X_text, X_dense])
    clf = LogisticRegression(max_iter=1000, class_weight='balanced', n_jobs=1)
    clf.fit(X, labels)
    return TfidfLogRegBackend(clf, vectorizer, adapter, adapter.feature_keys or [], lexicon.hash(), clf.classes_.tolist())


def train_hashing_backend(texts: List[str], labels: List[str], lexicon: Lexicon = DEFAULT_LEXICON, *, n_features: int = 2**18, alternate_sign: bool = True, ngram_range=(1,2)) -> HashingLogRegBackend:
    texts = _augment_with_metadata(texts)
    adapter, dense_dicts = _fit_dense_adapter(texts, lexicon)
    hv = HashingVectorizer(n_features=n_features, alternate_sign=alternate_sign, ngram_range=ngram_range, lowercase=True, strip_accents='unicode')
    X_h = hv.transform(texts)
    tfidf = TfidfTransformer()
    X_text = tfidf.fit_transform(X_h)
    X_dense = adapter.transform(dense_dicts)
    from scipy.sparse import hstack
    X = hstack([X_text, X_dense])
    clf = LogisticRegression(max_iter=1000, class_weight='balanced', n_jobs=1)
    clf.fit(X, labels)
    backend = HashingLogRegBackend(clf, adapter, adapter.feature_keys or [], lexicon.hash(), clf.classes_.tolist(), n_features=n_features, ngram_range=ngram_range, alternate_sign=alternate_sign)
    # Inject learned idf into backend's transformer
    backend._tfidf.idf_ = tfidf.idf_  # type: ignore[attr-defined]
    return backend


def save_backend(backend: ModelBackend, out_dir: str | Path, meta: Dict[str, Any]):  # pragma: no cover simple wrapper
    backend.save(out_dir, meta)


def load_backend(model_dir: str | Path) -> ModelBackend:  # pragma: no cover simple IO
    d = Path(model_dir)
    obj = joblib.load(d / 'model.joblib')
    backend_name = obj.get('backend')
    if backend_name == 'tfidf':
        return TfidfLogRegBackend(obj['model'], obj['vectorizer'], obj['dense_adapter'], obj['feature_keys'], obj['lexicon_hash'], obj['labels'])
    if backend_name == 'hashing':
        backend = HashingLogRegBackend(obj['model'], obj['dense_adapter'], obj['feature_keys'], obj['lexicon_hash'], obj['labels'], n_features=obj['n_features'], ngram_range=tuple(obj.get('ngram_range', (1,2))), alternate_sign=obj.get('alternate_sign', True))
        # restore idf
        if obj.get('tfidf_idf') is not None:
            backend._tfidf.idf_ = obj['tfidf_idf']  # type: ignore[attr-defined]
        return backend
    if backend_name == 'distilbert':
        return DistilBERTBackend(
            obj['model_head'],
            obj['dense_adapter'],
            obj['feature_keys'],
            obj['lexicon_hash'],
            obj['labels'],
            hf_model=obj.get('hf_model','distilbert-base-uncased'),
            pooling=obj.get('pooling','cls'),
            max_seq_len=obj.get('max_seq_len',256),
            embed_batch_size=obj.get('embed_batch_size',16),
            use_dense=obj.get('use_dense', True),
            hidden_dim=obj.get('hidden_dim',768)
        )
    # legacy format (no backend key) -> adapt
    return load_legacy_adapter(obj)


class LegacyAdapter(ModelBackend):
    backend_name = 'legacy_tfidf'
    def __init__(self, obj):
        self._model = obj['model']
        self._vectorizer = obj['vectorizer']
        self._dense_adapter = obj['dense_adapter']
        self._feature_keys = obj['feature_keys']
        self._lexicon_hash = obj['lexicon_hash']
        self._labels = obj['labels']

    @property
    def labels(self):
        return self._labels

    @property
    def lexicon_hash(self):
        return self._lexicon_hash

    def predict_proba(self, texts: List[str], lexicon: Lexicon = DEFAULT_LEXICON):
        dense_dicts = [extract_features(t, lexicon).features for t in texts]
        X_text = self._vectorizer.transform(texts)
        X_dense = self._dense_adapter.transform(dense_dicts)
        from scipy.sparse import hstack
        X = hstack([X_text, X_dense])
        probs = self._model.predict_proba(X)
        out: List[Dict[str, float]] = []
        for row in probs:
            out.append({lab: float(row[i]) for i, lab in enumerate(self._labels)})
        return out

    def save(self, out_dir: str | Path, meta: Dict[str, Any]):  # pragma: no cover - not expected to save legacy
        raise NotImplementedError("Cannot save using legacy adapter")


def load_legacy_adapter(obj) -> LegacyAdapter:  # pragma: no cover direct mapping
    return LegacyAdapter(obj)


def train_backend(name: str, texts: List[str], labels: List[str], lexicon: Lexicon = DEFAULT_LEXICON, **kwargs) -> ModelBackend:
    name = name.lower()
    if name == 'tfidf':
        return train_tfidf_backend(texts, labels, lexicon, max_features=kwargs.get('max_features', 20000))
    if name == 'hashing':
        return train_hashing_backend(texts, labels, lexicon, n_features=kwargs.get('n_features', 2**18), alternate_sign=kwargs.get('alternate_sign', True))
    if name == 'distilbert':
        texts = _augment_with_metadata(texts)
        return train_distilbert_backend(
            texts, labels, lexicon,
            hf_model=kwargs.get('hf_model','distilbert-base-uncased'),
            pooling=kwargs.get('pooling','cls'),
            max_seq_len=kwargs.get('max_seq_len',256),
            embed_batch_size=kwargs.get('embed_batch_size',16),
            use_dense=kwargs.get('use_dense', True)
        )
    raise ValueError(f"Unknown backend: {name}")


__all__ = [
    'ModelBackend','TfidfLogRegBackend','HashingLogRegBackend','train_backend','save_backend','load_backend','LABELS'
]

# =================== Optional Transformer (DistilBERT) Backend ===================
try:  # optional heavy deps
    import torch  # type: ignore
    from transformers import AutoTokenizer, AutoModel  # type: ignore
    _HAS_TRANSFORMERS = True
except Exception:  # pragma: no cover - absence path
    _HAS_TRANSFORMERS = False


class DistilBERTBackend(ModelBackend):
    backend_name = 'distilbert'

    def __init__(self, model_head, dense_adapter: DenseFeatureAdapter, feature_keys: List[str], lexicon_hash: str, labels: List[str], *, hf_model: str, pooling: str = 'cls', max_seq_len: int = 256, embed_batch_size: int = 16, use_dense: bool = True, hidden_dim: int = 768):
        self._model_head = model_head
        self._dense_adapter = dense_adapter
        self._feature_keys = feature_keys
        self._lexicon_hash = lexicon_hash
        self._labels = labels
        self._hf_model = hf_model
        self._pooling = pooling
        self._max_seq_len = max_seq_len
        self._embed_batch_size = embed_batch_size
        self._use_dense = use_dense
        self._hidden_dim = hidden_dim
        self._tok = None
        self._enc_model = None

    @property
    def labels(self):
        return self._labels

    @property
    def lexicon_hash(self):
        return self._lexicon_hash

    def _lazy_load(self):  # pragma: no cover - straightforward
        if self._tok is None or self._enc_model is None:
            if not _HAS_TRANSFORMERS:
                raise RuntimeError("Transformers not installed; install transformers torch to use distilbert backend")
            self._tok = AutoTokenizer.from_pretrained(self._hf_model)
            self._enc_model = AutoModel.from_pretrained(self._hf_model)
            self._enc_model.eval()

    def _embed_batch(self, batch: List[str]):  # returns np.ndarray [B, hidden]
        self._lazy_load()
        assert self._tok and self._enc_model
        with torch.no_grad():
            inputs = self._tok(batch, padding=True, truncation=True, max_length=self._max_seq_len, return_tensors='pt')
            outputs = self._enc_model(**inputs)
            if self._pooling == 'cls':
                emb = outputs.last_hidden_state[:,0,:]  # [B, H]
            else:  # mean pooling
                emb = outputs.last_hidden_state.mean(dim=1)
            return emb.cpu().numpy()

    def _embed_texts(self, texts: List[str]):
        vecs = []
        for i in range(0, len(texts), self._embed_batch_size):
            batch = texts[i:i+self._embed_batch_size]
            vecs.append(self._embed_batch(batch))
        if vecs:
            import numpy as _np
            return _np.vstack(vecs)
        import numpy as _np
        return _np.zeros((0, self._hidden_dim))

    def predict_proba(self, texts: List[str], lexicon: Lexicon = DEFAULT_LEXICON):
        if not texts:
            return []
        import numpy as _np
        emb = self._embed_texts(texts)
        if self._use_dense:
            dense_dicts = [extract_features(t, lexicon).features for t in texts]
            X_dense = self._dense_adapter.transform(dense_dicts)
            X = _np.hstack([emb, X_dense])
        else:
            X = emb
        probs = self._model_head.predict_proba(X)
        out: List[Dict[str, float]] = []
        for row in probs:
            out.append({lab: float(row[i]) for i, lab in enumerate(self._labels)})
        return out

    def save(self, out_dir: str | Path, meta: Dict[str, Any]):  # pragma: no cover
        d = Path(out_dir)
        d.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            'backend': self.backend_name,
            'model_head': self._model_head,
            'dense_adapter': self._dense_adapter,
            'feature_keys': self._feature_keys,
            'lexicon_hash': self._lexicon_hash,
            'labels': self._labels,
            'hf_model': self._hf_model,
            'pooling': self._pooling,
            'max_seq_len': self._max_seq_len,
            'embed_batch_size': self._embed_batch_size,
            'use_dense': self._use_dense,
            'hidden_dim': self._hidden_dim,
        }, d / 'model.joblib')
        meta_path = d / 'meta.json'
        meta['saved_at'] = time.time()
        meta['lexicon_hash'] = self._lexicon_hash
        meta['backend'] = self.backend_name
        meta['hf_model'] = self._hf_model
        meta_path.write_text(json.dumps(meta, indent=2), encoding='utf-8')


def train_distilbert_backend(texts: List[str], labels: List[str], lexicon: Lexicon = DEFAULT_LEXICON, *, hf_model: str = 'distilbert-base-uncased', pooling: str = 'cls', max_seq_len: int = 256, embed_batch_size: int = 16, use_dense: bool = True) -> DistilBERTBackend:
    if not _HAS_TRANSFORMERS:
        raise RuntimeError("Transformers not installed; run pip install transformers torch to use distilbert backend")
    # Extract dense features first (reuse existing adapter)
    dense_dicts = [extract_features(t, lexicon).features for t in texts]
    adapter = DenseFeatureAdapter()
    adapter.fit(dense_dicts)
    tok = AutoTokenizer.from_pretrained(hf_model)
    enc_model = AutoModel.from_pretrained(hf_model)
    enc_model.eval()
    import torch
    import numpy as _np
    embs = []
    with torch.no_grad():
        for i in range(0, len(texts), embed_batch_size):
            batch = texts[i:i+embed_batch_size]
            inputs = tok(batch, padding=True, truncation=True, max_length=max_seq_len, return_tensors='pt')
            outputs = enc_model(**inputs)
            if pooling == 'cls':
                emb = outputs.last_hidden_state[:,0,:]
            else:
                emb = outputs.last_hidden_state.mean(dim=1)
            embs.append(emb.cpu().numpy())
    if embs:
        X_text = _np.vstack(embs)
    else:
        hidden_dim = enc_model.config.hidden_size
        X_text = _np.zeros((0, hidden_dim))
    hidden_dim = X_text.shape[1]
    if use_dense:
        X_dense = adapter.transform(dense_dicts)
        X = _np.hstack([X_text, X_dense])
    else:
        X = X_text
    clf = LogisticRegression(max_iter=1000, class_weight='balanced', n_jobs=1)
    clf.fit(X, labels)
    backend = DistilBERTBackend(clf, adapter, adapter.feature_keys or [], lexicon.hash(), clf.classes_.tolist(), hf_model=hf_model, pooling=pooling, max_seq_len=max_seq_len, embed_batch_size=embed_batch_size, use_dense=use_dense, hidden_dim=hidden_dim)
    return backend

