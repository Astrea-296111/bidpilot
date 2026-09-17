async def evaluate(service, fixtures):
    rows = []
    for path in fixtures:
        tender = await service.repository.create_tender(path.stem, path)
        try:
            report = await service.analyze(tender.id)
            # Save approval is tested in E2E, eval intentionally rejects simulated opportunities.
            citations = [eid for m in report["matches"] for eid in m["evidence_ids"]]
            valid = sum(eid in report["evidence"] for eid in citations)
            row = {
                "file": path.name,
                "task_success": bool(report["decision"] and report["approval_required"]),
                "retry": report["retry_count"] > 0,
                "citations": len(citations),
                "valid_citations": valid,
                **report["metrics"],
                "score": report["decision"]["score"],
                "recommendation": report["decision"]["recommendation"],
            }
            await service.analyze(tender.id, approval=False)
        except Exception as exc:
            row = {"file": path.name, "task_success": False, "error": type(exc).__name__}
        rows.append(row)
    good = [r for r in rows if r["task_success"]]
    total_citations = sum(r["citations"] for r in good)
    return {
        "cases": len(rows),
        "task_success_rate": len(good) / len(rows),
        "reviewer_retry_rate": sum(r["retry"] for r in good) / len(good) if good else None,
        "average_retrieval_calls": sum(r["retrieval_calls"] for r in good) / len(good) if good else None,
        "average_tool_calls": sum(r["tool_calls"] for r in good) / len(good) if good else None,
        "average_latency_ms": sum(r["latency_ms"] for r in good) / len(good) if good else None,
        "citation_validity_rate": sum(r["valid_citations"] for r in good) / total_citations
        if total_citations
        else None,
        "success_definition": "grounded requirements, matrix, score, outline, HITL interrupt; not business correctness",
    }, rows
