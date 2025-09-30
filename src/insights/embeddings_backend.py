"""Sentence embedding backend (SBERT) with lazy loading.

Provides encode(texts, model_name, pca=None) -> np.ndarray

If sentence-transformers isn't installed, raises ImportError with guidance.
PCA: pass a fitted sklearn.decomposition.PCA instance or an int (n_components)
to trigger on-the-fly fit (NOT recommended at inference time). For training we
can fit PCA once and persist with joblib.
"""
from __future__ import annotations
from functools import lru_cache
from typing import List, Union, Optional

import numpy as np


@lru_cache(maxsize=2)
def load_model(model_name: str):
	try:
		from sentence_transformers import SentenceTransformer  # type: ignore
		return SentenceTransformer(model_name)
	except ImportError as e:
		msg = str(e)
		if 'cached_download' in msg:
			raise ImportError(
				"sentence-transformers / huggingface_hub version mismatch (cached_download missing). Upgrade sentence-transformers >=2.5 or pin huggingface_hub to earlier version."
			) from e
		raise ImportError(
			"sentence-transformers not installed or incompatible. Add/upgrade in requirements: sentence-transformers"
		) from e


def encode(texts: List[str], model_name: str = "sentence-transformers/all-MiniLM-L6-v2", pca=None) -> np.ndarray:
	mdl = load_model(model_name)
	emb = mdl.encode(texts, batch_size=32, show_progress_bar=False, convert_to_numpy=True, normalize_embeddings=True)
	if pca is not None:
		from sklearn.decomposition import PCA
		if isinstance(pca, int):
			# Fit PCA on the fly (training scenario only)
			pc = PCA(n_components=pca, random_state=42)
			emb = pc.fit_transform(emb)
		else:
			emb = pca.transform(emb)
	return emb

__all__ = ["encode", "load_model"]
