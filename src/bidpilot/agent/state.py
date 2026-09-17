from typing import TypedDict


class BidState(TypedDict, total=False):
    tender_id: str
    project_name: str
    source_file: str
    deadline: str | None
    document_sections: list[dict]
    requirements: list[dict]
    matches: list[dict]
    evidence: dict
    evidence_by_requirement: dict
    tool_calls: list[dict]
    reviewer_result: dict
    retry_count: int
    retry_requirement_ids: list[str]
    decision: dict
    response_outline: list[dict]
    warnings: list[str]
    extraction_incomplete: bool
    phase: str
    iterations: int
    metrics: dict
    messages: list[dict]
    approved: bool
    saved_opportunity: dict
    status: str
