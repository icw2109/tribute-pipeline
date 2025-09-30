"""Vectorizer registry to allow pluggable text -> feature encodings.

Current backends:
 - tfidf (default): uses sklearn.feature_extraction.text.TfidfVectorizer
 - sbert: sentence-transformers embeddings via embeddings_backend.encode

Unified interface:
  vec = get_vectorizer(backend, **kwargs)
  X = vec.fit_transform(texts)  # training
  X = vec.transform(texts)      # inference

SBERT backend returns dense numpy arrays; TF-IDF returns sparse matrices.
Both are accepted by sklearn LogisticRegression (which densifies if needed).
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Any, Optional

import numpy as np


@dataclass
class BaseVectorizer:
	backend: str
	def fit_transform(self, texts: List[str]):
		raise NotImplementedError
	def transform(self, texts: List[str]):
		raise NotImplementedError
	def save(self, path):
		import joblib
		joblib.dump(self, path)
	# Loading handled via joblib.load


class TfidfBackend(BaseVectorizer):
	def __init__(self, max_features: int = 20000, ngram_range=(1,2), min_df: int = 1):
		from sklearn.feature_extraction.text import TfidfVectorizer
		self.backend = 'tfidf'
		self.vec = TfidfVectorizer(max_features=max_features, ngram_range=ngram_range, min_df=min_df)
	def fit_transform(self, texts: List[str]):
		return self.vec.fit_transform(texts)
	def transform(self, texts: List[str]):
		return self.vec.transform(texts)
	def get_feature_names_out(self):
		return self.vec.get_feature_names_out()


class SbertBackend(BaseVectorizer):
	def __init__(self, model_name: str):
		self.backend = 'sbert'
		self.model_name = model_name
	def fit_transform(self, texts: List[str]):
		from .embeddings_backend import encode
		return encode(texts, model_name=self.model_name)
	def transform(self, texts: List[str]):
		from .embeddings_backend import encode
		return encode(texts, model_name=self.model_name)
	def get_feature_names_out(self):  # For compatibility in explanations
		return np.array([])


def get_vectorizer(backend: str = 'tfidf', **kwargs) -> BaseVectorizer:
	backend = (backend or 'tfidf').lower()
	if backend == 'tfidf':
		return TfidfBackend(
			max_features=kwargs.get('max_features', 20000),
			ngram_range=kwargs.get('ngram_range', (1,2)),
			min_df=kwargs.get('min_df', 1)
		)
	if backend == 'sbert':
		model_name = kwargs.get('model_name', 'sentence-transformers/all-MiniLM-L6-v2')
		return SbertBackend(model_name=model_name)
	raise ValueError(f"Unknown vectorizer backend '{backend}'")

__all__ = ["get_vectorizer", "TfidfBackend", "SbertBackend", "BaseVectorizer"]
