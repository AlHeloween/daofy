"""
Embedding service — provides true semantic search for the knowledge base

Uses the intfloat/multilingual-e5-small model:
- Chinese-English bilingual support
- Runs locally on CPU, no API dependency
- Automatic degradation: returns None when the model is not installed / fails to load, and the caller falls back

The model is about 70MB; the first load takes about 1-2s, later loads <100ms
"""

import logging
import os
import site
import threading
from typing import Any, List, Optional

logger = logging.getLogger(__name__)

# numpy is an optional dependency — without it the KB's basic features are unaffected; only semantic search degrades to the inverted index
np: Any = None  # type: ignore
numpy: Any = None  # type: ignore
try:
    import numpy  # noqa: F401
    import numpy as np
except ImportError:
    pass

# Ensure the user site-packages is on the path (pip install defaults to the user directory)
if site.USER_SITE is not None:
    try:
        site.addsitedir(site.USER_SITE)
    except Exception:
        logger.debug("Ignoring non-fatal exception: site.addsitedir")

# Global singleton
_model = None
_model_name = "intfloat/multilingual-e5-small"
_MODEL_LOAD_TIMEOUT = 60  # model load timeout in seconds (including download)
_env_lock = threading.Lock()  # guards os.environ thread safety


def is_available() -> bool:
    """Check whether the embedding dependencies are available"""
    if np is None:
        return False
    try:
        import sentence_transformers  # noqa: F401
        return True
    except ImportError:
        return False


def is_model_loaded() -> bool:
    """Check whether the model is loaded (a quick test for searches; does not trigger loading)"""
    return _model is not None


def load_model(timeout: int = None):
    """Lazily load the model (global singleton), with timeout protection.

    Args:
        timeout: timeout in seconds; None uses the _MODEL_LOAD_TIMEOUT default.
            After the timeout it returns None, to avoid blocking the MCP tool call.
    """
    global _model
    if _model is not None:
        return _model

    if timeout is None:
        timeout = _MODEL_LOAD_TIMEOUT

    from sentence_transformers import SentenceTransformer

    # Try several mirror sources
    # The user can force one via the HF_ENDPOINT environment variable
    default_endpoint = os.environ.get("HF_ENDPOINT")
    _endpoints = []
    if default_endpoint:
        _endpoints = [default_endpoint]
    else:
        _endpoints = [
            None,  # huggingface.co (default)
            "https://hf-mirror.com",
        ]

    # Save the original environment variables and restore them on exit
    _saved_env = {
        'HF_ENDPOINT': os.environ.get('HF_ENDPOINT'),
        'TRANSFORMERS_OFFLINE': os.environ.get('TRANSFORMERS_OFFLINE'),
        'HF_HUB_OFFLINE': os.environ.get('HF_HUB_OFFLINE'),
    }

    def _restore_env():
        with _env_lock:
            for k, v in _saved_env.items():
                if v is not None:
                    os.environ[k] = v
                else:
                    os.environ.pop(k, None)

    def _try_load(endpoint):
        """Try loading the model from the given endpoint (runs in a child thread, interruptible by the timeout)"""
        result = [None]  # pass the result through a list (shared reference across threads)
        error = [None]
        def _worker():
            try:
                if endpoint:
                    logger.info(f"Loading embedding model (mirror: {endpoint}): {_model_name}")
                    with _env_lock:
                        os.environ["HF_ENDPOINT"] = endpoint
                else:
                    logger.info(f"Loading embedding model: {_model_name}")

                # Prefer offline mode
                with _env_lock:
                    os.environ["TRANSFORMERS_OFFLINE"] = "1"
                    os.environ["HF_HUB_OFFLINE"] = "1"
                m = SentenceTransformer(_model_name, local_files_only=True)
                logger.info("embedding model loaded (offline mode)")
                result[0] = m
                return
            except Exception as e:
                logger.warning(f"  Mirror {endpoint or 'default'} failed to load offline: {e}; trying an online download...")
                with _env_lock:
                    os.environ.pop("TRANSFORMERS_OFFLINE", None)
                    os.environ.pop("HF_HUB_OFFLINE", None)
                try:
                    m = SentenceTransformer(_model_name, local_files_only=False)
                    logger.info("embedding model loaded (online mode)")
                    result[0] = m
                except Exception as e2:
                    logger.warning(f"  Mirror {endpoint or 'default'} also failed to load online: {e2}")
                    error[0] = e2

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join(timeout=timeout)
        if thread.is_alive():
            # The thread is still running after the timeout (a daemon thread terminates automatically when the main process exits)
            logger.warning(f"Timed out loading the embedding model ({timeout}s), mirror {endpoint or 'default'}")
            _restore_env()
            return None
        if result[0] is not None:
            _restore_env()
            return result[0]
        _restore_env()
        return None

    for ep in _endpoints:
        m = _try_load(ep)
        if m is not None:
            _model = m
            return _model

    logger.warning("No mirror could load the embedding model (or loading timed out)")
    return None


def encode_texts(texts: List[str], prefix: str = "query") -> Optional[Any]:
    """
    Encode a list of texts and return normalized embedding arrays

    Args:
        texts: list of texts
        prefix: E5 prefix — "query" for searches, "passage" for indexing

    Returns:
        numpy.ndarray shape=(n, 384); normalized, so a dot product is the cosine
        Returns None on failure
    """
    model = load_model()
    if model is None:
        return None

    try:
        prefixed = [f"{prefix}: {t}" for t in texts]
        # normalize_embeddings=True ensures the output is normalized, so dot = cosine
        embeddings = model.encode(prefixed, normalize_embeddings=True, show_progress_bar=False)
        return np.array(embeddings, dtype=np.float32)
    except Exception as e:
        logger.warning(f"embedding encoding failed: {e}")
        return None


def encode_single(text: str, prefix: str = "query") -> Optional[Any]:
    """Encode a single text"""
    result = encode_texts([text], prefix=prefix)
    if result is not None:
        return result[0]
    return None


def cosine_similarity(query_emb: Any, db_embs: Any) -> Optional[Any]:
    """
    Compute the cosine similarity between the query and a batch of vectors

    Args:
        query_emb: (dim,) normalized query vector
        db_embs: (n, dim) normalized vector matrix

    Returns:
        (n,) similarity scores, or None when numpy is unavailable
    """
    if np is None:
        return None
    # Already normalized → dot = cosine
    return np.dot(db_embs, query_emb)


def blob_to_vector(blob: bytes) -> Optional[Any]:
    """SQLite BLOB → numpy vector"""
    if np is None:
        return None
    try:
        return np.frombuffer(blob, dtype=np.float32)
    except Exception:
        return None


def batch_encode_and_store(cursor, rows, prefix: str = "passage") -> int:
    """
    Batch-encode vocabularies and write them into the vector column

    Args:
        cursor: SQLite cursor
        rows: [(id, name), ...] list of (vocab_id, name) to encode
        prefix: E5 prefix

    Returns:
        The number successfully encoded and written
    """
    if np is None:
        return 0

    if not rows:
        return 0

    names = [r[1] for r in rows]
    embs = encode_texts(names, prefix=prefix)
    if embs is None:
        return 0

    count = 0
    for (vid, _), vec in zip(rows, embs):
        if vec is not None and not np.all(vec == 0):
            blob = vec.tobytes()
            cursor.execute(
                "UPDATE vocabularies SET vector=?, vector_status='ready' WHERE id=?",
                (blob, vid)
            )
            count += 1
    return count
