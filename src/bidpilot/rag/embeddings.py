import hashlib
import json
from pathlib import Path
from typing import Protocol

import numpy as np

from bidpilot.rag.bm25 import tokenize


class EmbeddingProvider(Protocol):
    dimensions: int
    name: str

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedding:
    """Offline lexical hashing baseline. This is NOT a semantic language model."""

    dimensions = 512
    name = "deterministic-hash-512-v1"

    def embed(self, texts):
        result = []
        for text in texts:
            v = np.zeros(self.dimensions)
            for term in tokenize(text):
                digest = hashlib.sha256(term.encode()).digest()
                v[int.from_bytes(digest[:4], "little") % self.dimensions] += 1
            norm = np.linalg.norm(v)
            result.append((v / norm if norm else v).tolist())
        return result


class LocalEmbedding:
    def __init__(self, model):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model, device="cpu")
        self.dimensions = self.model.get_sentence_embedding_dimension()
        self.name = model

    def embed(self, texts):
        return self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


class APIEmbedding:
    def __init__(self, settings):
        from openai import OpenAI

        self.client = OpenAI(
            api_key=settings.embedding_api_key,
            base_url=settings.embedding_base_url,
            timeout=30,
            max_retries=1,
        )
        self.name = settings.embedding_model
        self.dimensions = settings.embedding_dimensions

    def embed(self, texts):
        response = self.client.embeddings.create(model=self.name, input=texts)
        result = [x.embedding for x in sorted(response.data, key=lambda x: x.index)]
        if any(len(x) != self.dimensions for x in result):
            raise ValueError("Embedding dimension differs from EMBEDDING_DIMENSIONS")
        return result


class CachedEmbedding:
    def __init__(self, provider, directory: Path):
        self.provider = provider
        self.dimensions, self.name = provider.dimensions, provider.name
        self.directory = directory
        directory.mkdir(parents=True, exist_ok=True)

    def embed(self, texts):
        result, missing, positions, paths = [None] * len(texts), [], [], []
        for i, text in enumerate(texts):
            key = hashlib.sha256(f"{self.name}:{self.dimensions}:{text}".encode()).hexdigest()
            path = self.directory / f"{key}.json"
            try:
                result[i] = json.loads(path.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                missing.append(text)
                positions.append(i)
                paths.append(path)
        if missing:
            for i, path, vector in zip(positions, paths, self.provider.embed(missing), strict=True):
                result[i] = vector
                path.write_text(json.dumps(vector))
        return result


class UnavailableEmbedding:
    """Keep Full mode honest: use BM25 when a real model cannot initialize, never fake semantics."""

    def __init__(self, settings, reason):
        self.dimensions = settings.embedding_dimensions
        self.name = f"unavailable:{settings.embedding_model}"
        self.reason = reason

    def embed(self, texts):
        raise RuntimeError(f"Embedding initialization failed: {self.reason}")


def create_embedding(settings):
    if settings.embedding_provider == "hash":
        provider = HashEmbedding()
    elif settings.embedding_provider == "api":
        provider = APIEmbedding(settings)
    else:
        try:
            provider = LocalEmbedding(settings.embedding_model)
        except Exception as exc:
            provider = UnavailableEmbedding(settings, type(exc).__name__)
    return CachedEmbedding(provider, settings.runtime_dir / "embeddings")
