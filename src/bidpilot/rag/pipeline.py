import asyncio
import hashlib
import json
import threading

from bidpilot.agent.schemas import Evidence
from bidpilot.rag.bm25 import BM25Index
from bidpilot.rag.chunker import chunk_document
from bidpilot.rag.embeddings import create_embedding
from bidpilot.rag.reranker import Reranker
from bidpilot.rag.rrf import reciprocal_rank_fusion
from bidpilot.rag.vector_store import CompanyKnowledgeVectorStore

CATEGORY_FILTER = {
    "qualification": ["certifications", "company"],
    "technical": ["technical", "products"],
    "delivery": ["services", "technical"],
    "commercial": ["services", "company"],
    "scoring": ["cases", "historical_bids", "products", "technical"],
}


class RAGPipeline:
    def __init__(self, settings, cache):
        self.settings, self.cache = settings, cache
        self.embedding = create_embedding(settings)
        self.vector = CompanyKnowledgeVectorStore(settings, self.embedding.dimensions)
        self.reranker = Reranker(settings.enable_reranker, settings.reranker_model)
        self.chunks, self.warnings, self.version = [], [], ""
        self.bm25 = BM25Index([])
        self.lock = threading.RLock()
        self.vector_ready = False

    def reindex(self):
        with self.lock:
            chunks = []
            for root in (self.settings.knowledge_dir, self.settings.runtime_dir / "knowledge"):
                for path in sorted(root.rglob("*")):
                    if path.suffix.lower() in {".md", ".txt", ".pdf", ".docx"}:
                        chunks.extend(
                            chunk_document(
                                path, root, self.settings.chunk_size, self.settings.chunk_overlap
                            )
                        )
            self.chunks, self.bm25 = chunks, BM25Index(chunks)
            self.version = hashlib.sha256("".join(c.evidence_id for c in chunks).encode()).hexdigest()
            self.warnings = []
            try:
                self.vector.replace(chunks, self.embedding.embed([x.chunk_text for x in chunks]))
                self.vector_ready = True
            except Exception as exc:
                self.vector_ready = False
                self.warnings.append(f"Vector/embedding unavailable: {type(exc).__name__}; BM25 only")
            return {
                "documents": len({c.document_id for c in chunks}),
                "chunks": len(chunks),
                "warnings": self.warnings,
            }

    def search_sync(self, query, categories=None, mode="hybrid", limit=4):
        with self.lock:
            bm = self.bm25.search(query, categories, 10) if mode != "vector" else []
            vec = []
            if mode != "bm25" and self.vector_ready:
                try:
                    vec = self.vector.search(self.embedding.embed([query])[0], categories, 10)
                except Exception as exc:
                    self.warnings.append(f"Vector query failed: {type(exc).__name__}")
            if mode == "vector":
                return vec[:limit]
            if mode == "bm25":
                return bm[:limit]
            fused = reciprocal_rank_fusion([vec, bm], limit=8)
            return self.reranker.rank(query, fused, limit) if mode == "rerank" else fused[:limit]

    async def retrieve(self, query, category=None, retry=False):
        filters = None if retry else CATEGORY_FILTER.get(category)
        mode = "rerank" if self.settings.enable_reranker else "hybrid"
        key = (
            "retrieval:"
            + hashlib.sha256(
                json.dumps([self.version, self.embedding.name, query, filters, mode]).encode()
            ).hexdigest()
        )
        cached = await self.cache.get(key)
        if cached is not None:
            return [Evidence.model_validate(x) for x in cached]
        result = await asyncio.to_thread(self.search_sync, query, filters, mode)
        await self.cache.set(key, [x.model_dump() for x in result])
        return result

    def close(self):
        self.vector.close()
