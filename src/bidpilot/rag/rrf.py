def reciprocal_rank_fusion(rankings, k=60, limit=8):
    scores, evidence = {}, {}
    for ranking in rankings:
        seen = set()
        for rank, item in enumerate(ranking, 1):
            key = item.evidence_id
            if key in seen:
                continue
            seen.add(key)
            evidence[key] = item
            scores[key] = scores.get(key, 0) + 1 / (k + rank)
    ids = sorted(scores, key=lambda x: (-scores[x], x))[:limit]
    return [evidence[x].model_copy(update={"score": scores[x]}) for x in ids]
