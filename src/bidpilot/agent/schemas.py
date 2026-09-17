from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["mandatory", "technical", "qualification", "commercial", "delivery", "scoring"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Requirement(StrictModel):
    requirement_id: str
    text: str = Field(min_length=2, max_length=3000)
    category: Category
    mandatory: bool = False
    weight: float | None = Field(None, ge=0, le=100)
    source_page: int | None = Field(None, ge=1)
    source_section: str | None = None
    source_quote: str = ""


class RequirementExtractionResult(StrictModel):
    project_name: str | None = None
    deadline: str | None = None
    requirements: list[Requirement]


class Evidence(StrictModel):
    evidence_id: str
    document_id: str
    title: str
    category: str
    source: str
    chunk_index: int
    updated_at: str
    tags: list[str] = Field(default_factory=list)
    chunk_text: str
    score: float = 0


class CapabilityMatch(StrictModel):
    requirement_id: str
    status: Literal["MATCH", "PARTIAL", "GAP"]
    confidence: float = Field(ge=0, le=1)
    evidence_ids: list[str] = Field(default_factory=list)
    explanation: str
    missing_items: list[str] = Field(default_factory=list)


class ReviewResult(StrictModel):
    passed: bool
    issues: list[str] = Field(default_factory=list)
    retry_requirement_ids: list[str] = Field(default_factory=list)


class QueryPlan(StrictModel):
    queries: list[str] = Field(min_length=1, max_length=2)
    tool: Literal[
        "none",
        "get_company_profile",
        "get_product_capability",
        "get_qualification",
        "get_case_study",
        "get_historical_bid",
    ] = "none"
    product: str = "data_platform"
    keyword: str = ""
    industry: str = "banking"


class OutlineSection(StrictModel):
    title: str
    requirement_ids: list[str]
    evidence_ids: list[str]


class ResponseOutline(StrictModel):
    sections: list[OutlineSection]


class ChatAnswer(StrictModel):
    answer: str
    evidence_ids: list[str]
