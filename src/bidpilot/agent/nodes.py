import asyncio
from pathlib import Path

from langgraph.config import get_stream_writer
from langgraph.types import interrupt

from bidpilot.agent.schemas import (
    CapabilityMatch,
    QueryPlan,
    Requirement,
    RequirementExtractionResult,
    ResponseOutline,
    ReviewResult,
)
from bidpilot.documents.parser import normalize_requirements, normalize_text, parse_document
from bidpilot.matching.scoring import calculate_score
from bidpilot.mcp_client.approval import sign_approval
from bidpilot.mcp_client.client import EnterpriseMCPClient


def emit(event, **data):
    try:
        get_stream_writer()({"event": event, "data": data})
    except RuntimeError:
        pass


def metric_copy(state):
    return {
        "llm_calls": 0,
        "retrieval_calls": 0,
        "tool_calls": 0,
        "latency_ms": 0,
        **state.get("metrics", {}),
    }


class AgentNodes:
    def __init__(self, settings, llm, rag):
        self.settings, self.llm, self.rag = settings, llm, rag
        self.mcp = EnterpriseMCPClient(settings)

    async def supervisor(self, state):
        iterations = state.get("iterations", 0) + 1
        if iterations > self.settings.max_graph_steps // 2:
            return {
                "phase": "stop",
                "status": "budget_exceeded",
                "iterations": iterations,
                "warnings": state.get("warnings", []) + ["Supervisor iteration budget exceeded"],
            }
        return {"iterations": iterations}

    async def parse(self, state):
        sections = await asyncio.to_thread(
            parse_document, Path(state["source_file"]), self.settings.max_document_chars
        )
        return {"document_sections": [s.model_dump() for s in sections], "phase": "analyst"}

    async def analyst(self, state):
        metrics, warnings = metric_copy(state), list(state.get("warnings", []))
        requirements, deadline = [], None
        # Bound each model context; never silently truncate an entire RFP.
        batches, batch, length = [], [], 0
        for section in state["document_sections"]:
            for offset in range(0, len(section["text"]), 5500):
                part = {**section, "text": section["text"][offset : offset + 5500]}
                if length + len(part["text"]) > 6000 and batch:
                    batches.append(batch)
                    batch, length = [], 0
                batch.append(part)
                length += len(part["text"])
        if batch:
            batches.append(batch)
        project_name = state["project_name"]
        for sections in batches:
            metrics["llm_calls"] += 1
            result = await self.llm.structured(
                "requirement_analyst",
                RequirementExtractionResult,
                {"sections": sections, "project_name": project_name},
            )
            project_name = result.project_name or project_name
            deadline = result.deadline or deadline
            for requirement in result.requirements:
                source = next(
                    (
                        s
                        for s in sections
                        if requirement.source_quote
                        and normalize_text(requirement.source_quote) in normalize_text(s["text"])
                    ),
                    None,
                )
                if source is None:
                    warnings.append(
                        f"Rejected ungrounded extracted requirement: {requirement.text[:80]}"
                    )
                    continue
                requirement.source_page, requirement.source_section = source["page"], source["title"]
                requirements.append(requirement)
        requirements = normalize_requirements(requirements)
        if not requirements:
            raise ValueError(
                "No grounded requirements extracted; Lite supports explicit bullet requirements"
            )
        if len(requirements) > self.settings.max_requirements:
            raise ValueError(
                "Too many requirements; split the tender to stay within the configured budget"
            )
        missing = []
        for section in state["document_sections"]:
            for line in section["text"].splitlines():
                if any(word in line for word in ("必须", "不得", "强制")) and not any(
                    normalize_text(r.source_quote) in normalize_text(line) for r in requirements
                ):
                    missing.append(line[:100])
        if missing:
            warnings.append("Potential omitted mandatory clauses: " + " | ".join(missing))
        return {
            "requirements": [r.model_dump() for r in requirements],
            "deadline": deadline,
            "project_name": project_name,
            "metrics": metrics,
            "warnings": warnings,
            "extraction_incomplete": bool(missing) or any("Rejected ungrounded" in w for w in warnings),
            "phase": "matcher",
            "retry_count": 0,
        }

    def tool_arguments(self, plan):
        return {
            "get_qualification": {"qualification_name": plan.keyword},
            "get_product_capability": {"product": plan.product, "capability": plan.keyword},
            "get_case_study": {"industry": plan.industry, "keyword": None},
            "get_historical_bid": {"industry": plan.industry, "keyword": plan.keyword},
            "get_company_profile": {"section": None},
        }.get(plan.tool, {})

    async def matcher(self, state):
        warnings, metrics = list(state.get("warnings", [])), metric_copy(state)
        evidence, per_req = (
            dict(state.get("evidence", {})),
            dict(state.get("evidence_by_requirement", {})),
        )
        matches = {m["requirement_id"]: m for m in state.get("matches", [])}
        calls = list(state.get("tool_calls", []))
        retry = state.get("retry_count", 0) > 0
        requirements = [
            r
            for r in state["requirements"]
            if not retry or r["requirement_id"] in state.get("retry_requirement_ids", [])
        ]

        async def process(session=None):
            for index, requirement in enumerate(requirements):
                rid = requirement["requirement_id"]
                metrics["llm_calls"] += 1
                try:
                    plan = await self.llm.structured(
                        "query_rewrite", QueryPlan, {"requirement": requirement}
                    )
                except Exception as exc:
                    warnings.append(f"Query rewrite fallback: {type(exc).__name__}")
                    plan = QueryPlan(queries=[requirement["text"]], tool="none")
                retrieved = {}
                for query in plan.queries:
                    metrics["retrieval_calls"] += 1
                    for chunk in await self.rag.retrieve(query, requirement["category"], retry):
                        retrieved[chunk.evidence_id] = chunk.model_dump()
                evidence.update(retrieved)
                per_req[rid] = sorted(set(per_req.get(rid, [])) | set(retrieved))
                observation = {}
                # Reserve one call for the explicitly approved write at the end.
                if (
                    session
                    and plan.tool != "none"
                    and metrics["tool_calls"] < self.settings.max_tool_calls - 1
                ):
                    metrics["tool_calls"] += 1
                    args = self.tool_arguments(plan)
                    try:
                        observation = await self.mcp.call(session, plan.tool, args)
                        calls.append({"name": plan.tool, "arguments": args, "result": observation})
                    except Exception as exc:
                        warnings.append(
                            f"Read MCP unavailable: {type(exc).__name__}; using RAG evidence"
                        )
                        calls.append({"name": plan.tool, "arguments": args, "error": type(exc).__name__})
                emit("retrieval", requirement_id=rid, evidence_ids=list(retrieved), queries=plan.queries)
                metrics["llm_calls"] += 1
                try:
                    match = await self.llm.structured(
                        "capability_matcher",
                        CapabilityMatch,
                        {
                            "requirement": requirement,
                            "evidence": list(retrieved.values())[:8],
                            "tool_observation": observation,
                            "review_feedback": state.get("reviewer_result"),
                        },
                    )
                    # The orchestration owns identifiers, not the model.
                    match.requirement_id = rid
                except Exception as exc:
                    warnings.append(f"Match fallback for {rid}: {type(exc).__name__}")
                    match = CapabilityMatch(
                        requirement_id=rid,
                        status="GAP",
                        confidence=0,
                        explanation="Model failure; capability not established",
                        missing_items=["人工核实"],
                    )
                matches[rid] = match.model_dump()
                emit("progress", current=index + 1, total=len(requirements), retry=retry)

        # The session is opened and closed within the same task (important for AnyIO/Windows).
        if metrics["tool_calls"] < self.settings.max_tool_calls - 1:
            from contextlib import AsyncExitStack

            async with AsyncExitStack() as stack:
                try:
                    session = await stack.enter_async_context(self.mcp.connect())
                except Exception as exc:
                    warnings.append(f"MCP connection unavailable: {type(exc).__name__}")
                    session = None
                await process(session)
        else:
            await process()
        return {
            "matches": [matches[r["requirement_id"]] for r in state["requirements"]],
            "evidence": evidence,
            "evidence_by_requirement": per_req,
            "tool_calls": calls,
            "metrics": metrics,
            "warnings": warnings,
            "phase": "reviewer",
        }

    async def reviewer(self, state):
        metrics, issues, retry, items = metric_copy(state), [], set(), []
        matches = {m["requirement_id"]: m for m in state["matches"]}
        for r in state["requirements"]:
            rid = r["requirement_id"]
            m = matches.get(rid)
            allowed = set(state["evidence_by_requirement"].get(rid, []))
            if m is None:
                retry.add(rid)
                issues.append(f"{rid}: missing match")
                continue
            if set(m["evidence_ids"]) - allowed or any(
                e not in state["evidence"] for e in m["evidence_ids"]
            ):
                retry.add(rid)
                issues.append(f"{rid}: invalid citation")
            if m["status"] in {"MATCH", "PARTIAL"} and not m["evidence_ids"]:
                retry.add(rid)
                issues.append(f"{rid}: unsupported positive conclusion")
            if m["confidence"] < 0.6:
                retry.add(rid)
                issues.append(f"{rid}: low confidence; broaden retrieval once")
            valid = [
                state["evidence"][eid]
                for eid in m["evidence_ids"]
                if eid in allowed and eid in state["evidence"]
            ]
            items.append({"requirement": r, "match": m, "evidence": valid})
        # Independent reviewer context contains cited evidence only, not matcher reasoning history.
        for offset in range(0, len(items), 4):
            metrics["llm_calls"] += 1
            try:
                review = await self.llm.structured(
                    "reviewer", ReviewResult, {"items": items[offset : offset + 4]}
                )
                issues.extend(review.issues)
                if not review.passed:
                    batch_ids = {i["requirement"]["requirement_id"] for i in items[offset : offset + 4]}
                    retry.update(set(review.retry_requirement_ids) & batch_ids or batch_ids)
            except Exception as exc:
                issues.append(f"Reviewer unavailable: {type(exc).__name__}")
                retry.update(i["requirement"]["requirement_id"] for i in items[offset : offset + 4])
        valid_ids = {r["requirement_id"] for r in state["requirements"]}
        retry &= valid_ids
        count = state.get("retry_count", 0)
        need_retry = bool(retry) and count < self.settings.max_retrieval_retry
        if retry and not need_retry:
            for rid in retry:
                m = matches[rid]
                m = {
                    **m,
                    "status": "GAP",
                    "confidence": min(m["confidence"], 0.5),
                    "evidence_ids": [
                        eid
                        for eid in m["evidence_ids"]
                        if eid in state["evidence_by_requirement"].get(rid, [])
                        and eid in state["evidence"]
                    ],
                    "missing_items": m["missing_items"] + ["复核后仍未证实；不作能力承诺"],
                    "explanation": m["explanation"] + " Reviewer 未通过，保守降为 GAP。",
                }
                matches[rid] = m
        result = ReviewResult(passed=not retry, issues=issues, retry_requirement_ids=sorted(retry))
        emit("review", passed=result.passed, retry=need_retry, issues=issues)
        return {
            "reviewer_result": result.model_dump(),
            "metrics": metrics,
            "matches": [matches[r["requirement_id"]] for r in state["requirements"]],
            "retry_requirement_ids": sorted(retry),
            "retry_count": count + int(need_retry),
            "phase": "matcher" if need_retry else "score",
        }

    async def score(self, state):
        decision = calculate_score(
            [Requirement.model_validate(r) for r in state["requirements"]],
            [CapabilityMatch.model_validate(m) for m in state["matches"]],
            self.settings.project_root / "config/scoring.yaml",
        )
        if state.get("extraction_incomplete"):
            decision["recommendation"] = "NO_BID"
            decision["blocking_reason"] = "Extraction incomplete; manual review required before bidding"
        return {"decision": decision, "phase": "outline"}

    async def outline(self, state):
        metrics, warnings = metric_copy(state), list(state.get("warnings", []))
        metrics["llm_calls"] += 1
        payload = {"requirements": state["requirements"], "matches": state["matches"]}
        try:
            result = await self.llm.structured("response_outline", ResponseOutline, payload)
            req_ids = {r["requirement_id"] for r in state["requirements"]}
            used = {eid for m in state["matches"] for eid in m["evidence_ids"]}
            if any(
                set(s.requirement_ids) - req_ids or set(s.evidence_ids) - used for s in result.sections
            ):
                raise ValueError("Invalid outline references")
            for section in result.sections:
                scoped = {
                    eid
                    for m in state["matches"]
                    if m["requirement_id"] in section.requirement_ids
                    for eid in m["evidence_ids"]
                }
                if set(section.evidence_ids) - scoped:
                    raise ValueError("Outline citation belongs to a different requirement")
            if {rid for s in result.sections for rid in s.requirement_ids} != req_ids:
                raise ValueError("Outline omitted requirements")
        except Exception as exc:
            from bidpilot.llm.fake import FakeLLMProvider

            warnings.append(f"Outline template fallback: {type(exc).__name__}")
            result = await FakeLLMProvider().structured("response_outline", ResponseOutline, payload)
        return {
            "response_outline": [s.model_dump() for s in result.sections],
            "metrics": metrics,
            "warnings": warnings,
            "status": "awaiting_review",
            "phase": "human_review",
            "messages": [
                {
                    "role": "assistant",
                    "content": f"{state['project_name']}: {state['decision']['recommendation']}",
                }
            ],
        }

    def opportunity_payload(self, state):
        return {
            "tender_id": state["tender_id"],
            "project_name": state["project_name"],
            "deadline": state.get("deadline"),
            "score": state["decision"]["score"],
            "recommendation": state["decision"]["recommendation"],
        }

    async def human_review(self, state):
        choice = interrupt(
            {
                "question": "确认将本次分析保存为投标机会？这不会提交标书。",
                **self.opportunity_payload(state),
            }
        )
        approved = isinstance(choice, dict) and choice.get("approve") is True
        return {
            "approved": approved,
            "phase": "save" if approved else "stop",
            "status": "approved" if approved else "rejected",
        }

    async def save(self, state):
        if not state.get("approved"):
            raise ValueError("Cannot save without human approval")
        metrics = metric_copy(state)
        if metrics["tool_calls"] >= self.settings.max_tool_calls:
            return {
                "status": "save_failed",
                "phase": "stop",
                "warnings": state.get("warnings", []) + ["Tool budget exhausted before save"],
            }
        payload = self.opportunity_payload(state)
        token = sign_approval(payload, self.settings.approval_secret)
        metrics["tool_calls"] += 1
        try:
            async with self.mcp.connect() as session:
                result = await self.mcp.call(
                    session,
                    "save_bid_opportunity",
                    {**payload, "approval_token": token},
                    allow_write=True,
                )
            return {
                "saved_opportunity": result,
                "status": "saved",
                "phase": "stop",
                "metrics": metrics,
                "tool_calls": state.get("tool_calls", [])
                + [{"name": "save_bid_opportunity", "arguments": payload, "result": result}],
            }
        except Exception as exc:
            return {
                "status": "save_failed",
                "phase": "stop",
                "metrics": metrics,
                "warnings": state.get("warnings", []) + [f"MCP save failed: {type(exc).__name__}"],
            }
