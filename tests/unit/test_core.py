import asyncio

import pytest
from pydantic import ValidationError

from bidpilot.agent.schemas import CapabilityMatch, Evidence, QueryPlan, Requirement
from bidpilot.cache.store import MemoryCache
from bidpilot.documents.parser import normalize_requirements, parse_document
from bidpilot.matching.scoring import calculate_score
from bidpilot.matching.support import assess
from bidpilot.mcp_client.approval import sign_approval, verify_approval
from bidpilot.rag.bm25 import BM25Index, tokenize
from bidpilot.rag.chunker import chunk_document
from bidpilot.rag.embeddings import HashEmbedding
from bidpilot.rag.rrf import reciprocal_rank_fusion


def evidence(key="EV-a", text="支持 Kubernetes 私有化部署。", category="technical"):
    return Evidence(
        evidence_id=key,
        document_id="a.md",
        title="a",
        category=category,
        source="a.md",
        chunk_index=0,
        updated_at="2026-09-16",
        chunk_text=text,
    )


def test_schema_rejects_invalid_status_confidence_and_extra_fields():
    with pytest.raises(ValidationError):
        CapabilityMatch(requirement_id="r", status="YES", confidence=2, explanation="x", fake=True)
    with pytest.raises(ValidationError):
        QueryPlan(queries=["a", "b", "c"])


def test_normalize_preserves_mandatory_and_largest_weight():
    a = Requirement(
        requirement_id="a", text="支持 Kubernetes", category="technical", mandatory=False, weight=2
    )
    b = a.model_copy(update={"text": "支持Kubernetes。", "mandatory": True, "weight": 5})
    result = normalize_requirements([a, b])
    assert len(result) == 1 and result[0].mandatory and result[0].weight == 5


def test_rrf_rank_fusion_and_duplicates():
    a, b = evidence(), evidence("EV-b")
    result = reciprocal_rank_fusion([[a, b, b], [b]], k=60)
    assert result[0].evidence_id == b.evidence_id
    assert result[0].score == pytest.approx(1 / 62 + 1 / 61)


def test_bm25_exact_technical_terms_and_filter():
    index = BM25Index(
        [
            evidence("a", "ISO27001 认证", "certifications"),
            evidence("b", "Kubernetes 部署"),
            evidence("c", "技术服务"),
        ]
    )
    assert index.search("ISO27001", ["certifications"])[0].evidence_id == "a"
    assert not index.search("ISO27001", ["technical"])
    assert "99.95%" in tokenize("SLA 99.95%")


def test_embedding_determinism_and_norm():
    import numpy as np

    provider = HashEmbedding()
    a, b = provider.embed(["Kubernetes 部署", "Kubernetes 部署"])
    assert a == b and np.linalg.norm(a) == pytest.approx(1)


def test_chunk_metadata(settings):
    p = settings.knowledge_dir / "technical/kubernetes_deployment.md"
    chunks = chunk_document(p, settings.knowledge_dir, size=80, overlap=10)
    assert len(chunks) > 1
    assert all(c.category == "technical" and c.source.endswith(".md") for c in chunks)
    assert len({c.evidence_id for c in chunks}) == len(chunks)


@pytest.mark.parametrize("suffix", [".md", ".pdf", ".docx"])
def test_parser_preserves_requirements(settings, suffix):
    path = settings.project_root / ("data/rfps/01-bank-data-platform" + suffix)
    sections = parse_document(path)
    assert "Kubernetes" in "\n".join(s.text for s in sections)
    if suffix == ".pdf":
        assert all(s.page is not None for s in sections)


def test_empty_and_invalid_pdf_rejected(tmp_path):
    path = tmp_path / "broken.pdf"
    path.write_bytes(b"not a PDF")
    with pytest.raises(ValueError, match="解析失败"):
        parse_document(path)


def test_mandatory_qualification_gap_veto(settings):
    r = Requirement(
        requirement_id="r", text="必须具备 ISO20000", category="qualification", mandatory=True
    )
    m = CapabilityMatch(requirement_id="r", status="GAP", confidence=0.9, explanation="No certification")
    result = calculate_score([r], [m], settings.project_root / "config/scoring.yaml")
    assert result["recommendation"] == "NO_BID" and result["score"] == 0


def test_missing_dimensions_reweight_and_mandatory_partial(settings):
    r = Requirement(requirement_id="r", text="技术支持5年", category="delivery", mandatory=True)
    m = CapabilityMatch(requirement_id="r", status="PARTIAL", confidence=0.8, explanation="3 years only")
    result = calculate_score([r], [m], settings.project_root / "config/scoring.yaml")
    assert result["score"] == 50 and result["coverage"]["technical"]["ratio"] is None


@pytest.mark.parametrize(
    "query,text,status",
    [
        ("必须支持 SAML", "尚未支持 SAML 协议。", "GAP"),
        ("支持 OIDC 和 SAML", "支持 OIDC。\n不支持 SAML。", "PARTIAL"),
        ("可用性不低于 99.99%", "可用性 99.95%", "PARTIAL"),
        ("RTO 10 分钟", "RTO 30 分钟", "PARTIAL"),
        ("ISO20000", "公司未取得 ISO20000 认证。", "GAP"),
    ],
)
def test_evidence_numeric_and_negative_rules(query, text, status):
    assert assess(query, [evidence(text=text)])[0] == status


def test_signed_human_approval_is_payload_bound():
    data = {"score": 80, "tender_id": "one"}
    token = sign_approval(data, "secret")
    assert verify_approval(data, token, "secret")
    assert not verify_approval({**data, "score": 99}, token, "secret")
    assert not verify_approval(data, token, "wrong")
    assert not verify_approval(data, sign_approval(data, "secret", 1), "secret")


async def test_cache_counter_atomic_and_ttl():
    cache = MemoryCache()
    counts = await asyncio.gather(*(cache.increment("rate") for _ in range(25)))
    assert sorted(counts) == list(range(1, 26))
    await cache.set("expired", 1, ttl=0)
    assert await cache.get("expired") is None
