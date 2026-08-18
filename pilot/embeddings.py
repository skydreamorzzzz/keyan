"""Embedding utilities for retrieval experiments.

Uses sentence-transformers for question/text embeddings.
"""
import numpy as np
from sentence_transformers import SentenceTransformer

# Global model instance (lazy loaded)
_model = None

def get_embedding_model():
    """Get or initialize the embedding model."""
    global _model
    if _model is None:
        # Use all-MiniLM-L6-v2: fast, good quality, 384 dims
        _model = SentenceTransformer('all-MiniLM-L6-v2')
    return _model

def get_embedding(text: str) -> np.ndarray:
    """Compute embedding for a single text string.

    Returns:
        numpy array of shape (embedding_dim,)
    """
    model = get_embedding_model()
    embedding = model.encode(text, convert_to_numpy=True)
    return embedding

def get_embeddings_batch(texts: list) -> np.ndarray:
    """Compute embeddings for a batch of texts.

    Returns:
        numpy array of shape (n_texts, embedding_dim)
    """
    model = get_embedding_model()
    embeddings = model.encode(texts, convert_to_numpy=True, show_progress_bar=True)
    return embeddings
