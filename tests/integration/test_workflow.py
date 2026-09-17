import pytest
from sqlalchemy import select

from bidpilot.agent.nodes import AgentNodes
from bidpilot.agent.schemas import CapabilityMatch, Requirement
from bidpilot.llm.fake import FakeLLMProvider
from bidpilot.mcp_client.approval import sign_approval
from bidpilot.mcp_client.client import EnterpriseMCPClient
from bidpilot.persistence.models import Opportunity
from bidpilot.service import BidPilotService


async def test_mcp_real_stdio_reads_and_signed_idempotent_write(settings):
    client = EnterpriseMCPClient(settings)
    async with client.connect() as session:
        names = {t.name for t in (await session.list_tools()).tools}
        assert len(names) == 6 and "save_bid_opportunity" in names
        profile = await client.call(session, "get_company_profile", {})
        assert profile["data"]["name"] == "AuroraSoft"
        missing = await client.call(session, "get_qualification", {"qualification_name": "SOC2"})
        assert missing["found"] is False
        payload = {
            "tender_id": "mcp-integration",
            "project_name": "测试",
            "deadline": None,
            "score": 82.0,
            "recommendation": "BID",
        }
        with pytest.raises(ValueError, match="not allowed"):
            await client.call(session, "save_bid_opportunity", payload)
        with pytest.raises(RuntimeError):
            await client.call(
                session, "save_bid_opportunity", {**payload, "approval_token": "forged"}, True
            )
        args = {**payload, "approval_token": sign_approval(payload, settings.approval_secret)}
        first = await client.call(session, "save_bid_opportunity", args, True)
        second = await client.call(session, "save_bid_opportunity", args, True)
        assert first["saved"] and second["already_existed"]


async def test_checkpoint_survives_service_restart_and_reject_does_not_save(settings):
    async with BidPilotService(settings) as service:
        tender = await service.repository.create_tender(
            "bank", settings.project_root / "data/rfps/01-bank-data-platform.md"
        )
        report = await service.analyze(tender.id)
        assert report["approval_required"] and report["status"] == "awaiting_review"
        assert report["decision"]["recommendation"] == "BID"
        assert report["metrics"]["tool_calls"] > 0
    async with BidPilotService(settings) as service:
        report = await service.analyze(tender.id, approval=False)
        assert report["status"] == "rejected"
        async with service.repository.sessions() as session:
            assert await session.scalar(select(Opportunity)) is None
        with pytest.raises(ValueError, match="not awaiting"):
            await service.analyze(tender.id, approval=True)


async def test_qdrant_filter_and_retry_for_real_gap(settings):
    async with BidPilotService(settings) as service:
        chunks = await service.rag.retrieve("ISO27001", "qualification")
        assert chunks and all(e.category in {"certifications", "company"} for e in chunks)
        tender = await service.repository.create_tender(
            "gap", settings.project_root / "data/rfps/05-qualification-gap.md"
        )
        report = await service.analyze(tender.id)
        assert report["retry_count"] == 1
        assert report["decision"]["recommendation"] == "NO_BID"
        assert report["metrics"]["tool_calls"] <= settings.max_tool_calls
        assert all(eid in report["evidence"] for m in report["matches"] for eid in m["evidence_ids"])


async def test_reviewer_rejects_fabricated_citation(settings):
    r = Requirement(
        requirement_id="REQ-001", text="必须支持 Kubernetes", category="technical", mandatory=True
    )
    m = CapabilityMatch(
        requirement_id=r.requirement_id,
        status="MATCH",
        confidence=0.99,
        evidence_ids=["EV-forged"],
        explanation="fabricated",
    )
    state = {
        "requirements": [r.model_dump()],
        "matches": [m.model_dump()],
        "evidence": {},
        "evidence_by_requirement": {r.requirement_id: []},
        "retry_count": 0,
    }
    nodes = AgentNodes(settings, FakeLLMProvider(), None)
    first = await nodes.reviewer(state)
    assert first["phase"] == "matcher" and first["retry_count"] == 1
    second = await nodes.reviewer({**state, "retry_count": 1})
    assert second["phase"] == "score"
    assert second["matches"][0]["status"] == "GAP"
    assert second["matches"][0]["evidence_ids"] == []


async def test_mcp_failure_degrades_without_invented_evidence(settings, monkeypatch):
    async with BidPilotService(settings) as service:

        async def broken(*args, **kwargs):
            raise ConnectionError("test MCP outage")

        monkeypatch.setattr(EnterpriseMCPClient, "call", broken)
        tender = await service.repository.create_tender(
            "bank", settings.project_root / "data/rfps/14-minimal-rfp.md"
        )
        report = await service.analyze(tender.id)
        assert report["approval_required"]
        assert any("MCP unavailable" in w for w in report["warnings"])
        saved = await service.analyze(tender.id, approval=True)
        assert saved["status"] == "save_failed"


async def test_graph_budget_fails_with_persisted_status(settings):
    settings.max_graph_steps = 10
    async with BidPilotService(settings) as service:
        tender = await service.repository.create_tender(
            "limited", settings.project_root / "data/rfps/14-minimal-rfp.md"
        )
        with pytest.raises(Exception):
            await service.analyze(tender.id)
        assert (await service.repository.get_tender(tender.id)).status == "failed"
