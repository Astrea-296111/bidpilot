import yaml


def calculate_score(requirements, matches, config_path):
    config = yaml.safe_load(config_path.read_text(encoding="utf-8"))["bid"]
    by_id = {m.requirement_id: m for m in matches}
    groups = {
        "mandatory": [r for r in requirements if r.mandatory],
        "qualification": [r for r in requirements if r.category == "qualification"],
        "technical": [r for r in requirements if r.category in {"technical", "mandatory"}],
        "experience": [r for r in requirements if r.category == "scoring"],
        "service": [r for r in requirements if r.category in {"delivery", "commercial"}],
    }
    values = {"MATCH": 1, "PARTIAL": 0.5, "GAP": 0}
    coverage, weighted, active = {}, 0, 0
    for name, reqs in groups.items():
        total = sum(r.weight if r.weight is not None else 1 for r in reqs)
        if not reqs or total == 0:
            coverage[name] = {"ratio": None, "count": len(reqs), "note": "N/A; weight renormalized"}
            continue
        earned = sum(
            (r.weight if r.weight is not None else 1) * values[by_id[r.requirement_id].status]
            if r.requirement_id in by_id
            else 0
            for r in reqs
        )
        ratio = earned / total
        coverage[name] = {"ratio": round(ratio, 4), "count": len(reqs), "earned": earned, "total": total}
        weight = config["weights"][name]
        weighted += ratio * weight
        active += weight
    gaps = [
        r
        for r in requirements
        if r.mandatory and (r.requirement_id not in by_id or by_id[r.requirement_id].status == "GAP")
    ]
    score = (
        round(max(0, 100 * weighted / active - len(gaps) * config["mandatory_gap_penalty"]), 2)
        if active
        else 0
    )
    recommendation = (
        "BID"
        if score >= config["bid_threshold"]
        else "CONDITIONAL_BID"
        if score >= config["conditional_threshold"]
        else "NO_BID"
    )
    if gaps and recommendation == "BID":
        recommendation = "CONDITIONAL_BID"
    if any(r.category in config["severe_gap_categories"] for r in gaps):
        recommendation = "NO_BID"
    # Mandatory PARTIAL also needs a human commitment, even at a high overall score.
    if recommendation == "BID" and any(
        r.mandatory and by_id[r.requirement_id].status != "MATCH" for r in requirements
    ):
        recommendation = "CONDITIONAL_BID"
    return {
        "score": score,
        "recommendation": recommendation,
        "coverage": coverage,
        "mandatory_gaps": [r.requirement_id for r in gaps],
        "rules": config,
    }
