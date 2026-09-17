from uuid import NAMESPACE_URL, uuid5

from qdrant_client import QdrantClient, models

from bidpilot.agent.schemas import Evidence


class CompanyKnowledgeVectorStore:
    def __init__(self, settings, dimensions):
        self.client = (
            QdrantClient(path=str(settings.runtime_dir / "qdrant"))
            if settings.mode == "lite"
            else QdrantClient(url=settings.qdrant_url, timeout=10)
        )
        self.dimensions = dimensions
        self.collection = settings.qdrant_collection

    def replace(self, chunks, vectors):
        if self.client.collection_exists(self.collection):
            self.client.delete_collection(self.collection)
        self.client.create_collection(
            self.collection,
            vectors_config=models.VectorParams(size=self.dimensions, distance=models.Distance.COSINE),
        )
        if chunks:
            self.client.upsert(
                self.collection,
                points=[
                    models.PointStruct(
                        id=str(uuid5(NAMESPACE_URL, c.evidence_id)), vector=v, payload=c.model_dump()
                    )
                    for c, v in zip(chunks, vectors, strict=True)
                ],
            )

    def search(self, vector, categories=None, limit=10):
        filters = (
            models.Filter(
                must=[models.FieldCondition(key="category", match=models.MatchAny(any=categories))]
            )
            if categories
            else None
        )
        response = self.client.query_points(
            self.collection, query=vector, query_filter=filters, limit=limit, with_payload=True
        )
        return [Evidence.model_validate({**p.payload, "score": p.score}) for p in response.points]

    def close(self):
        self.client.close()
