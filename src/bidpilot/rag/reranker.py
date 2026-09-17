class Reranker:
    def __init__(self, enabled=False, model="BAAI/bge-reranker-base"):
        self.enabled, self.model_name, self.model = enabled, model, None
        self.warning = None

    def rank(self, query, chunks, limit=4):
        if not self.enabled or not chunks:
            return chunks[:limit]
        try:
            if self.model is None:
                from sentence_transformers import CrossEncoder

                self.model = CrossEncoder(self.model_name, device="cpu")
            scores = self.model.predict([(query, c.chunk_text) for c in chunks])
            pairs = sorted(zip(chunks, scores, strict=True), key=lambda pair: -float(pair[1]))
            return [c.model_copy(update={"score": float(score)}) for c, score in pairs[:limit]]
        except Exception as exc:
            self.warning = f"Reranker unavailable ({type(exc).__name__}); retained RRF order"
            return chunks[:limit]
