import asyncio

from bidpilot.rag.pipeline import CATEGORY_FILTER


async def evaluate(rag, dataset, k=4):
    modes = ["vector", "bm25", "hybrid"] + (["rerank"] if rag.settings.enable_reranker else [])
    rows, summary = [], {}
    for mode in modes:
        batch = []
        for case in dataset:
            chunks = await asyncio.to_thread(
                rag.search_sync, case["query"], CATEGORY_FILTER.get(case["category"]), mode, k
            )
            docs = list(dict.fromkeys(c.document_id for c in chunks))
            expected = set(case["expected_docs"])
            hits = expected.intersection(docs)
            first = next((i for i, doc in enumerate(docs, 1) if doc in expected), None)
            row = {
                "id": case["id"],
                "mode": mode,
                "query": case["query"],
                "k": k,
                "recall_at_k": len(hits) / len(expected),
                "hit": int(bool(hits)),
                "rr": 1 / first if first else 0,
                "retrieved_docs": "|".join(docs),
                "expected_docs": "|".join(case["expected_docs"]),
            }
            batch.append(row)
        rows.extend(batch)
        summary[mode] = {
            "queries": len(batch),
            "k_chunks": k,
            "recall_at_k": sum(r["recall_at_k"] for r in batch) / len(batch),
            "hit_rate": sum(r["hit"] for r in batch) / len(batch),
            "mrr": sum(r["rr"] for r in batch) / len(batch),
        }
    if "rerank" not in summary:
        summary["rerank"] = "NOT_MEASURED (optional model disabled)"
    return summary, rows
