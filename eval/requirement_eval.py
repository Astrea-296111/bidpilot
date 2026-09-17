from bidpilot.agent.schemas import RequirementExtractionResult
from bidpilot.documents.parser import normalize_requirements, normalize_text, parse_document


async def evaluate(llm, root, dataset):
    tp = predicted = expected = mandatory_hit = mandatory_total = 0
    rows = []
    for case in dataset:
        sections = parse_document(root / "data/rfps" / case["file"])
        result = await llm.structured(
            "requirement_analyst",
            RequirementExtractionResult,
            {"sections": [s.model_dump() for s in sections], "project_name": case["file"]},
        )
        preds = normalize_requirements(result.requirements)
        p = {(normalize_text(r.text), r.category, r.mandatory) for r in preds}
        g = {(normalize_text(r["text"]), r["category"], r["mandatory"]) for r in case["requirements"]}
        overlap = p & g
        tp += len(overlap)
        predicted += len(p)
        expected += len(g)
        mandatory_hit += sum(item[2] for item in overlap)
        mandatory_total += sum(item[2] for item in g)
        rows.append(
            {
                "file": case["file"],
                "missing": [list(x) for x in g - p],
                "extra": [list(x) for x in p - g],
            }
        )
    precision = tp / predicted if predicted else 0
    recall = tp / expected if expected else 0
    return {
        "rfps": len(dataset),
        "gold_requirements": expected,
        "precision": precision,
        "recall": recall,
        "f1": 2 * precision * recall / (precision + recall) if precision + recall else 0,
        "mandatory_recall": mandatory_hit / mandatory_total if mandatory_total else None,
        "matching_method": "normalized exact text + category + mandatory; synthetic bullet fixtures",
    }, rows
