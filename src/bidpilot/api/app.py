import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, StrictBool

from bidpilot.config import Settings
from bidpilot.documents.parser import parse_document
from bidpilot.service import BidPilotService


class Approval(BaseModel):
    approve: StrictBool


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    tender_id: str | None = None
    thread_id: str | None = Field(None, max_length=100)


def create_app(settings=None):
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        async with BidPilotService(settings) as service:
            app.state.service = service
            yield

    app = FastAPI(title="BidPilot", version="0.1.0", lifespan=lifespan)

    @app.middleware("http")
    async def rate_limit(request: Request, call_next):
        if request.method == "POST":
            # No user auth in this local demo; use socket peer, never trust a client-supplied user header.
            peer = request.client.host if request.client else "local"
            count = await app.state.service.cache.increment(f"rate:{peer}")
            if count > settings.rate_limit:
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"detail": "Rate limit exceeded"}, status_code=429, headers={"Retry-After": "60"}
                )
        return await call_next(request)

    async def tender_or_404(tender_id):
        tender = await app.state.service.repository.get_tender(tender_id)
        if not tender:
            raise HTTPException(404, "Tender not found")
        return tender

    async def persist_upload(file, directory):
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in {".pdf", ".docx", ".md", ".txt"}:
            raise HTTPException(415, "Supported: PDF, DOCX, MD, TXT")
        data = await file.read(settings.max_upload_mb * 1024 * 1024 + 1)
        if len(data) > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, "Upload exceeds size limit")
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (uuid4().hex + suffix)
        await asyncio.to_thread(path.write_bytes, data)
        try:
            await asyncio.to_thread(parse_document, path, settings.max_document_chars)
        except ValueError as exc:
            path.unlink(missing_ok=True)
            raise HTTPException(422, str(exc)) from exc
        return path

    @app.get("/api/health")
    async def health():
        service = app.state.service
        return {
            "status": "degraded" if service.rag.warnings else "ok",
            "mode": settings.mode,
            "model": service.llm.model_name,
            "vector_ready": service.rag.vector_ready,
            "redis_degraded": getattr(service.cache, "degraded", False),
            "documents": len({c.document_id for c in service.rag.chunks}),
            "warnings": service.rag.warnings,
            "single_worker": True,
        }

    @app.post("/api/tenders/upload", status_code=201)
    async def upload_tender(file: UploadFile = File(...)):
        path = await persist_upload(file, settings.runtime_dir / "uploads")
        tender = await app.state.service.repository.create_tender(Path(file.filename).stem[:300], path)
        return {"id": tender.id, "project_name": tender.project_name, "status": tender.status}

    @app.post("/api/tenders/{tender_id}/analyze")
    async def analyze(tender_id: str, wait: bool = False):
        await tender_or_404(tender_id)
        if wait:
            try:
                return await app.state.service.analyze(tender_id)
            except ValueError as exc:
                raise HTTPException(409, str(exc)) from exc
        app.state.service.start_analysis(tender_id)
        return {
            "id": tender_id,
            "status": "accepted",
            "stream_url": f"/api/tenders/{tender_id}/analyze/stream",
        }

    @app.get("/api/tenders/{tender_id}/analyze/stream")
    async def stream(tender_id: str, request: Request):
        await tender_or_404(tender_id)
        try:
            after = max(0, int(request.headers.get("Last-Event-ID", "0")))
        except ValueError:
            raise HTTPException(400, "Invalid Last-Event-ID") from None
        return StreamingResponse(
            app.state.service.stream_events(tender_id, after),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/tenders/{tender_id}")
    async def get_tender(tender_id: str):
        row = await tender_or_404(tender_id)
        return {
            "id": row.id,
            "project_name": row.project_name,
            "deadline": row.deadline,
            "status": row.status,
            "error": row.error,
        }

    @app.get("/api/tenders/{tender_id}/report")
    async def get_report(tender_id: str):
        await tender_or_404(tender_id)
        report = await app.state.service.repository.get_report(tender_id)
        if not report:
            raise HTTPException(409, "Report not available yet")
        return report

    @app.get("/api/tenders/{tender_id}/requirements")
    async def requirements(tender_id: str):
        return (await get_report(tender_id))["requirements"]

    @app.get("/api/tenders/{tender_id}/matches")
    async def matches(tender_id: str):
        return (await get_report(tender_id))["matches"]

    @app.post("/api/tenders/{tender_id}/review")
    async def review(tender_id: str, body: Approval):
        await tender_or_404(tender_id)
        try:
            return await app.state.service.analyze(tender_id, approval=body.approve)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/knowledge/upload", status_code=201)
    async def upload_knowledge(
        file: UploadFile = File(...),
        category: Literal[
            "company", "products", "technical", "certifications", "cases", "services", "historical_bids"
        ] = Form("products"),
    ):
        path = await persist_upload(file, settings.runtime_dir / "knowledge" / category)
        return {
            "document_id": path.relative_to(settings.runtime_dir / "knowledge").as_posix(),
            "status": "uploaded",
            "next": "POST /api/knowledge/reindex",
        }

    @app.post("/api/knowledge/reindex")
    async def reindex():
        return await asyncio.to_thread(app.state.service.rag.reindex)

    @app.get("/api/knowledge/documents")
    async def documents():
        docs = {}
        for c in app.state.service.rag.chunks:
            docs.setdefault(
                c.document_id,
                {
                    "document_id": c.document_id,
                    "category": c.category,
                    "source": c.source,
                    "updated_at": c.updated_at,
                },
            )
        return list(docs.values())

    @app.post("/api/chat")
    async def chat(body: ChatRequest):
        try:
            return await app.state.service.chat(**body.model_dump())
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/api/chat/stream")
    async def chat_stream(body: ChatRequest):
        async def generate():
            yield 'event: node\ndata: {"node":"retrieval"}\n\n'
            try:
                answer = await app.state.service.chat(**body.model_dump())
                # Ground the complete answer before streaming presentation chunks.
                for i in range(0, len(answer["answer"]), 40):
                    yield (
                        "event: token\ndata: "
                        + json.dumps({"text": answer["answer"][i : i + 40]}, ensure_ascii=False)
                        + "\n\n"
                    )
                yield "event: result\ndata: " + json.dumps(answer, ensure_ascii=False) + "\n\n"
            except Exception as exc:
                yield "event: error\ndata: " + json.dumps({"message": type(exc).__name__}) + "\n\n"

        return StreamingResponse(generate(), media_type="text/event-stream")

    return app
