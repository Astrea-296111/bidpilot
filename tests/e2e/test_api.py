import pytest
from fastapi.testclient import TestClient

from bidpilot.api.app import create_app


@pytest.mark.parametrize("extension", ["pdf", "docx"])
def test_upload_analyze_sse_report_and_hitl_save(settings, extension):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["vector_ready"]
        path = settings.project_root / f"data/rfps/01-bank-data-platform.{extension}"
        response = client.post("/api/tenders/upload", files={"file": (path.name, path.read_bytes())})
        assert response.status_code == 201, response.text
        tid = response.json()["id"]
        response = client.post(f"/api/tenders/{tid}/analyze?wait=true")
        assert response.status_code == 200, response.text
        report = response.json()
        assert report["approval_required"] and report["requirements"] and report["matches"]
        assert report["decision"]["score"] >= 0
        stream = client.get(f"/api/tenders/{tid}/analyze/stream")
        assert "event: node" in stream.text and "event: retrieval" in stream.text
        assert "event: result" in stream.text and "text/event-stream" in stream.headers["content-type"]
        saved = client.post(f"/api/tenders/{tid}/review", json={"approve": True})
        assert saved.status_code == 200 and saved.json()["status"] == "saved", saved.text
        assert client.get(f"/api/tenders/{tid}/requirements").json()
        assert client.get(f"/api/tenders/{tid}/matches").json()
        assert client.get(f"/api/tenders/{tid}/report").json()["saved_opportunity"]["saved"]
        assert client.post(f"/api/tenders/{tid}/review", json={"approve": True}).status_code == 409
        answer = client.post("/api/chat", json={"message": "Kubernetes 私有化", "tender_id": tid}).json()
        assert answer["evidence_ids"] and answer["thread_id"]
        followup = client.post(
            "/api/chat/stream", json={"message": "还有什么要求？", "thread_id": answer["thread_id"]}
        )
        assert "event: token" in followup.text and tid in followup.text


def test_validation_and_knowledge_upload_reindex(settings):
    with TestClient(create_app(settings)) as client:
        assert client.get("/api/tenders/missing").status_code == 404
        assert (
            client.post("/api/tenders/upload", files={"file": ("x.exe", b"binary")}).status_code == 415
        )
        assert (
            client.post("/api/tenders/upload", files={"file": ("x.pdf", b"bad pdf")}).status_code == 422
        )
        assert client.post("/api/tenders/no/review", json={"approve": "yes"}).status_code == 422
        upload = client.post(
            "/api/knowledge/upload",
            files={"file": ("extra.md", "# 私有化\n支持私有化部署。".encode())},
            data={"category": "technical"},
        )
        assert upload.status_code == 201
        assert client.post("/api/knowledge/reindex").json()["documents"] == 26
        assert len(client.get("/api/knowledge/documents").json()) == 26


def test_rate_limit(settings):
    settings.rate_limit = 1
    with TestClient(create_app(settings)) as client:
        assert client.post("/api/chat", json={"message": "Kubernetes"}).status_code == 200
        assert client.post("/api/chat", json={"message": "Kubernetes"}).status_code == 429
