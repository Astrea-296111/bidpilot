from uuid import uuid4

from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from bidpilot.persistence.models import (
    AgentRun,
    Base,
    BidResult,
    ChatMemory,
    EvidenceRow,
    MatchRow,
    RequirementRow,
    Tender,
)


class Repository:
    def __init__(self, url):
        self.engine = create_async_engine(url)
        if url.startswith("sqlite"):

            @event.listens_for(self.engine.sync_engine, "connect")
            def configure_sqlite(connection, _):
                cursor = connection.cursor()
                cursor.execute("PRAGMA foreign_keys=ON")
                cursor.execute("PRAGMA busy_timeout=10000")
                cursor.close()

        self.sessions = async_sessionmaker(self.engine, expire_on_commit=False)

    async def initialize(self):
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    async def create_tender(self, name, path):
        tender = Tender(id=uuid4().hex, project_name=name, source_file=str(path))
        async with self.sessions.begin() as session:
            session.add(tender)
        return tender

    async def get_tender(self, tender_id):
        async with self.sessions() as session:
            return await session.get(Tender, tender_id)

    async def status(self, tender_id, status, error=None):
        async with self.sessions.begin() as session:
            tender = await session.get(Tender, tender_id)
            tender.status, tender.error = status, error

    async def get_report(self, tender_id):
        async with self.sessions() as session:
            result = await session.scalar(select(BidResult).where(BidResult.tender_id == tender_id))
            return result.summary if result else None

    async def save_report(self, tender_id, report):
        async with self.sessions.begin() as session:
            tender = await session.get(Tender, tender_id)
            tender.project_name = report["project_name"]
            tender.deadline = report.get("deadline")
            tender.status = report["status"]
            for r in report["requirements"]:
                rid = f"{tender_id}:{r['requirement_id']}"
                await session.merge(
                    RequirementRow(
                        id=rid,
                        tender_id=tender_id,
                        local_id=r["requirement_id"],
                        **{k: v for k, v in r.items() if k != "requirement_id"},
                    )
                )
            await session.flush()
            for m in report["matches"]:
                mid = f"{tender_id}:{m['requirement_id']}"
                await session.merge(
                    MatchRow(
                        id=mid,
                        requirement_id=mid,
                        **{k: v for k, v in m.items() if k not in {"requirement_id", "evidence_ids"}},
                    )
                )
            await session.flush()
            for m in report["matches"]:
                mid = f"{tender_id}:{m['requirement_id']}"
                for eid in m["evidence_ids"]:
                    e = report["evidence"][eid]
                    await session.merge(
                        EvidenceRow(
                            id=f"{mid}:{eid}",
                            match_id=mid,
                            document_id=e["document_id"],
                            chunk_id=eid,
                            score=e["score"],
                            snapshot=e,
                        )
                    )
            decision = report["decision"]
            await session.merge(
                BidResult(
                    id=tender_id,
                    tender_id=tender_id,
                    score=decision["score"],
                    recommendation=decision["recommendation"],
                    summary=report,
                )
            )
            metrics = report["metrics"]
            await session.merge(
                AgentRun(
                    id=tender_id,
                    tender_id=tender_id,
                    status=report["status"],
                    **{
                        k: metrics[k]
                        for k in ("llm_calls", "retrieval_calls", "tool_calls", "latency_ms")
                    },
                )
            )

    async def failed_run(self, tender_id, latency_ms):
        async with self.sessions.begin() as session:
            await session.merge(
                AgentRun(id=tender_id, tender_id=tender_id, status="failed", latency_ms=latency_ms)
            )

    async def chat_history(self, thread_id):
        async with self.sessions() as session:
            row = await session.get(ChatMemory, thread_id)
            return (row.tender_id, row.messages) if row else (None, [])

    async def save_chat(self, thread_id, tender_id, messages):
        async with self.sessions.begin() as session:
            await session.merge(
                ChatMemory(thread_id=thread_id, tender_id=tender_id, messages=messages[-8:])
            )

    async def close(self):
        await self.engine.dispose()
