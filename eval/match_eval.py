from bidpilot.agent.schemas import CapabilityMatch, Requirement


def classification_metrics(pairs):
    labels = ["MATCH", "PARTIAL", "GAP"]
    confusion = {truth: {pred: 0 for pred in labels} for truth in labels}
    for true, pred in pairs:
        confusion[true][pred] += 1
    f1s = []
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[t][label] for t in labels if t != label)
        fn = sum(confusion[label][p] for p in labels if p != label)
        f1s.append(2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0)
    return {
        "accuracy": sum(t == p for t, p in pairs) / len(pairs),
        "macro_f1": sum(f1s) / len(labels),
        "confusion": confusion,
    }


async def evaluate(llm, rag, dataset):
    rows = []
    for case in dataset:
        r = Requirement(
            requirement_id=case["id"],
            text=case["text"],
            category=case["category"],
            mandatory=case["mandatory"],
        )
        evidence = await rag.retrieve(r.text, r.category)
        match = await llm.structured(
            "capability_matcher",
            CapabilityMatch,
            {
                "requirement": r.model_dump(),
                "evidence": [e.model_dump() for e in evidence],
                "tool_observation": {},
            },
        )
        rows.append(
            {
                "id": case["id"],
                "text": case["text"],
                "expected": case["expected_status"],
                "predicted": match.status,
                "evidence_ids": match.evidence_ids,
            }
        )
    return {
        "cases": len(rows),
        **classification_metrics([(r["expected"], r["predicted"]) for r in rows]),
    }, rows
