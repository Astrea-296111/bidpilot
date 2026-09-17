import re

from rank_bm25 import BM25Okapi


def tokenize(text: str) -> list[str]:
    """Keep exact technical terms and Chinese uni/bigrams without downloading a tokenizer."""
    terms = re.findall(r"[a-z0-9]+(?:[./%-][a-z0-9]+)*%?", text.lower())
    for span in re.findall(r"[\u4e00-\u9fff]+", text):
        terms.extend(span)
        terms.extend(span[i : i + 2] for i in range(len(span) - 1))
    return terms or ["_empty_"]


class BM25Index:
    def __init__(self, chunks):
        self.chunks = chunks
        self.index = BM25Okapi([tokenize(x.chunk_text) for x in chunks]) if chunks else None

    def search(self, query, categories=None, limit=10):
        if self.index is None:
            return []
        scores = self.index.get_scores(tokenize(query))
        indices = sorted(range(len(scores)), key=lambda i: (-float(scores[i]), i))
        return [
            self.chunks[i].model_copy(update={"score": float(scores[i])})
            for i in indices
            if scores[i] > 0 and (not categories or self.chunks[i].category in categories)
        ][:limit]
