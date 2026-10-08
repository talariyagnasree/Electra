"""ChromaDB-backed semantic index of the course catalog."""
import hashlib
import re
import numpy as np
import chromadb
from chromadb import EmbeddingFunction
from chromadb.utils import embedding_functions
from .config import settings
from .models import Course

COLLECTION = "electives"
_client = None
_ef = None


class HashEmbedding(EmbeddingFunction):
    """Tiny offline bag-of-words hashing embedder (no model download needed)."""
    DIM = 384

    def __init__(self):
        pass

    def get_config(self):
        return {}

    @staticmethod
    def build_from_config(config):
        return HashEmbedding()

    @staticmethod
    def name() -> str:
        return "hash-embedding"

    def __call__(self, input):
        out = []
        for text in input:
            v = np.zeros(self.DIM, dtype=np.float32)
            for tok in re.findall(r"[a-z0-9+#]+", text.lower()):
                v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.DIM] += 1.0
            n = np.linalg.norm(v)
            out.append(v / n if n else v)
        return out


def _embedding_fn():
    global _ef
    if _ef is None:
        b = settings.embedding_backend
        if b == "hash":
            _ef = HashEmbedding()
        elif b == "openai":
            _ef = embedding_functions.OpenAIEmbeddingFunction(
                api_key=settings.llm_api_key, model_name="text-embedding-3-small")
        else:
            _ef = embedding_functions.DefaultEmbeddingFunction()
    return _ef


def _chroma():
    global _client
    if _client is None:
        settings.chroma_dir.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(settings.chroma_dir))
    return _client


def course_document(c: Course) -> str:
    return (f"{c.title}. Category: {c.category}. {c.description} "
            f"Topics: {', '.join(c.syllabus_topics)}. "
            f"Skills gained: {', '.join(c.skills_gained)}. "
            f"Career paths: {', '.join(c.career_paths)}.")


def _catalog_hash(courses: list[Course]) -> str:
    h = hashlib.sha256()
    h.update(settings.embedding_backend.encode())
    for c in sorted(courses, key=lambda x: x.code):
        h.update(c.code.encode())
        h.update(course_document(c).encode())
    return h.hexdigest()[:16]


def ensure_index(courses: list[Course], force: bool = False):
    """(Re)build the collection only when the catalog changed."""
    client, h = _chroma(), _catalog_hash(courses)
    if not force:
        try:
            col = client.get_collection(COLLECTION, embedding_function=_embedding_fn())
            if (col.metadata or {}).get("hash") == h and col.count() == len(courses):
                return col
        except Exception:
            pass
    try:
        client.delete_collection(COLLECTION)
    except Exception:
        pass
    col = client.create_collection(
        COLLECTION, embedding_function=_embedding_fn(),
        metadata={"hnsw:space": "cosine", "hash": h})
    if courses:
        col.add(ids=[c.code for c in courses],
                documents=[course_document(c) for c in courses],
                metadatas=[{"title": c.title, "category": c.category} for c in courses])
    return col


def similarities(query: str, courses: list[Course]) -> dict[str, float]:
    """code -> cosine similarity (0..1) for every course in the catalog."""
    col = ensure_index(courses)
    if not query.strip() or col.count() == 0:
        return {}
    res = col.query(query_texts=[query], n_results=col.count())
    return {i: max(0.0, min(1.0, 1 - d)) for i, d in zip(res["ids"][0], res["distances"][0])}


def search(query: str, courses: list[Course], k: int = 5) -> list[tuple[str, float]]:
    return sorted(similarities(query, courses).items(), key=lambda x: -x[1])[:k]
