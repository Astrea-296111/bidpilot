import asyncio
import json
import re
import time
from contextlib import AsyncExitStack
from uuid import uuid4

from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.errors import GraphRecursionError
from langgraph.types import Command

from bidpilot.agent.graph import build_graph
from bidpilot.agent.schemas import ChatAnswer
from bidpilot.cache.store import MemoryCache, RedisCache
from bidpilot.llm.fake import FakeLLMProvider
from bidpilot.llm.openai_compatible import OpenAICompatibleProvider
from bidpilot.persistence.repository import Repository
from bidpilot.rag.pipeline import RAGPipeline


class BidPilotService:
    def __init__(self, settings):
        self.settings = settings
        self.stack = AsyncExitStack()
        self.locks, self.events, self.tasks = {}, {}, {}
        self.chat_locks = {}

    async def __aenter__(self):
        self.settings.prepare()
        self.repository = Repository(self.settings.database_url)
        await self.repository.initialize()
        self.cache = (
            MemoryCache() if self.settings.mode == "lite" else RedisCache(self.settings.redis_url)
        )
        self.llm = (
            FakeLLMProvider()
            if self.settings.mode == "lite"
            else OpenAICompatibleProvider(self.settings)
        )
        self.rag = await asyncio.to_thread(RAGPipeline, self.settings, self.cache)
        await asyncio.to_thread(self.rag.reindex)
        saver = await self.stack.enter_async_context(
            AsyncSqliteSaver.from_conn_string(str(self.settings.runtime_dir / "checkpoints.sqlite"))
        )
        self.graph = build_graph(self.settings, self.llm, self.rag, saver)
        return self

    async def __aexit__(self, *args):
        for task in self.tasks.values():
            if not task.done():
                task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        await self.stack.aclose()
        await asyncio.to_thread(self.rag.close)
        await self.cache.close()
        await self.repository.close()

    def config(self, tender_id):
        return {
            "configurable": {"thread_id": tender_id},
            "recursion_limit": self.settings.max_graph_steps,
        }

    def publish(self, tender_id, event, data):
        history = self.events.setdefault(tender_id, [])
        history.append({"id": len(history) + 1, "event": event, "data": data})

    async def analyze(self, tender_id, approval=None):
        lock = self.locks.setdefault(tender_id, asyncio.Lock())
        if lock.locked():
            raise ValueError("Analysis already running")
        async with lock:
            tender = await self.repository.get_tender(tender_id)
            if tender is None:
                raise KeyError(tender_id)
            snapshot = await self.graph.aget_state(self.config(tender_id))
            if approval is not None:
                if not snapshot.next or "human_review" not in snapshot.next:
                    raise ValueError("Tender is not awaiting human confirmation")
                graph_input = Command(resume={"approve": approval})
            elif snapshot.values:
                existing = await self.repository.get_report(tender_id)
                if existing:
                    return existing
                if snapshot.next:
                    graph_input = None  # Resume a checkpoint after interrupted process execution.
                else:
                    raise ValueError("No resumable analysis; upload again to start a new run")
            else:
                graph_input = {
                    "tender_id": tender_id,
                    "project_name": tender.project_name,
                    "source_file": tender.source_file,
                    "phase": "parse",
                    "iterations": 0,
                    "status": "analyzing",
                    "warnings": [],
                    "metrics": {},
                    "tool_calls": [],
                }
            await self.repository.status(tender_id, "analyzing")
            await self.cache.set(f"analysis:{tender_id}", "analyzing")
            started = time.perf_counter()
            try:
                async for mode, chunk in self.graph.astream(
                    graph_input, self.config(tender_id), stream_mode=["updates", "custom"]
                ):
                    if mode == "custom":
                        self.publish(tender_id, chunk["event"], chunk["data"])
                    else:
                        for node, value in chunk.items():
                            if node == "__interrupt__":
                                self.publish(tender_id, "human_review", {"pending": True})
                            else:
                                self.publish(tender_id, "node", {"node": node})
                snapshot = await self.graph.aget_state(self.config(tender_id))
                state = snapshot.values
                if "decision" not in state:
                    raise RuntimeError(
                        "Workflow stopped before scoring (iteration budget or incomplete extraction)"
                    )
                elapsed = (time.perf_counter() - started) * 1000
                metrics = {
                    **state["metrics"],
                    "latency_ms": round(state["metrics"].get("latency_ms", 0) + elapsed, 2),
                }
                await self.graph.aupdate_state(self.config(tender_id), {"metrics": metrics})
                report = {
                    key: state.get(key)
                    for key in [
                        "tender_id",
                        "project_name",
                        "deadline",
                        "requirements",
                        "matches",
                        "evidence",
                        "reviewer_result",
                        "retry_count",
                        "decision",
                        "response_outline",
                        "status",
                        "saved_opportunity",
                        "extraction_incomplete",
                        "tool_calls",
                    ]
                }
                report["metrics"] = metrics
                report["model"] = self.llm.model_name
                report["embedding"] = self.rag.embedding.name
                report["simulated_company"] = True
                report["warnings"] = state.get("warnings", []) + self.rag.warnings
                if self.rag.reranker.warning:
                    report["warnings"].append(self.rag.reranker.warning)
                report["approval_required"] = bool(snapshot.next and "human_review" in snapshot.next)
                await self.repository.save_report(tender_id, report)
                await self.cache.set(f"analysis:{tender_id}", report["status"])
                self.publish(
                    tender_id,
                    "result",
                    {"tender_id": tender_id, "status": report["status"], "decision": report["decision"]},
                )
                return report
            except Exception as exc:
                message = (
                    "Graph step budget exceeded; checkpoint retained"
                    if isinstance(exc, GraphRecursionError)
                    else f"Analysis failed: {type(exc).__name__}: {str(exc)[:200]}"
                )
                await self.repository.status(tender_id, "failed", message)
                await self.repository.failed_run(tender_id, (time.perf_counter() - started) * 1000)
                await self.cache.set(f"analysis:{tender_id}", "failed")
                self.publish(tender_id, "error", {"message": message})
                raise

    def start_analysis(self, tender_id):
        existing = self.tasks.get(tender_id)
        if existing and not existing.done():
            return

        async def run():
            try:
                await self.analyze(tender_id)
            except Exception:
                pass  # Persisted and published by analyze; consumed by status and SSE APIs.

        self.tasks[tender_id] = asyncio.create_task(run())

    async def stream_events(self, tender_id, after=0):
        cursor = after
        heartbeat = time.monotonic()
        while True:
            history = self.events.get(tender_id, [])
            pending = [item for item in history if item["id"] > cursor]
            for item in pending:
                cursor = item["id"]
                yield f"id: {cursor}\nevent: {item['event']}\ndata: {json.dumps(item['data'], ensure_ascii=False)}\n\n"
                if item["event"] in {"result", "error"}:
                    return
            tender = await self.repository.get_tender(tender_id)
            running = tender and tender.status == "analyzing"
            task = self.tasks.get(tender_id)
            if not running and (task is None or task.done()):
                report = await self.repository.get_report(tender_id)
                if report:
                    yield (
                        "event: result\ndata: "
                        + json.dumps(
                            {
                                "tender_id": tender_id,
                                "status": report["status"],
                                "decision": report["decision"],
                            },
                            ensure_ascii=False,
                        )
                        + "\n\n"
                    )
                else:
                    yield 'event: status\ndata: {"message":"Start analysis with POST /analyze"}\n\n'
                return
            if time.monotonic() - heartbeat > 10:
                yield ": heartbeat\n\n"
                heartbeat = time.monotonic()
            await asyncio.sleep(0.1)

    async def chat(self, message, tender_id=None, thread_id=None):
        thread_id = thread_id or uuid4().hex
        async with self.chat_locks.setdefault(thread_id, asyncio.Lock()):
            prior_tender, history = await self.repository.chat_history(thread_id)
            tender_id = tender_id or prior_tender
            if tender_id != prior_tender:
                history = []
            context = await self.repository.get_report(tender_id) if tender_id else None
            if tender_id and not context:
                raise ValueError("Tender report not available")
            # Short-term history helps resolve follow-ups without sending full old reports.
            previous_user = next((m["content"] for m in reversed(history) if m["role"] == "user"), "")
            query = (previous_user + " " + message)[-2000:]
            evidence = await self.rag.retrieve(query)
            if context:
                evidence_map = {e.evidence_id: e.model_dump() for e in evidence}
                for m in context["matches"][:8]:
                    for eid in m["evidence_ids"][:1]:
                        evidence_map[eid] = context["evidence"][eid]
                evidence_dicts = list(evidence_map.values())[:8]
            else:
                evidence_dicts = [e.model_dump() for e in evidence]
            answer = await self.llm.structured(
                "chat",
                ChatAnswer,
                {
                    "question": message,
                    "history": history[-6:],
                    "tender_context": {
                        "project_name": context["project_name"],
                        "decision": context["decision"],
                    }
                    if context
                    else None,
                    "evidence": evidence_dicts,
                },
            )
            available = {e["evidence_id"] for e in evidence_dicts}
            inline_ids = set(re.findall(r"EV-[a-zA-Z0-9_-]+", answer.answer))
            if (
                set(answer.evidence_ids) - available
                or inline_ids - set(answer.evidence_ids)
                or not answer.evidence_ids
            ):
                answer = ChatAnswer(answer="资料不足，无法给出带有效引用的回答。", evidence_ids=[])
            await self.repository.save_chat(
                thread_id,
                tender_id,
                history
                + [
                    {"role": "user", "content": message},
                    {"role": "assistant", "content": answer.answer[:4000]},
                ],
            )
            return {
                **answer.model_dump(),
                "thread_id": thread_id,
                "tender_id": tender_id,
                "evidence": [e for e in evidence_dicts if e["evidence_id"] in answer.evidence_ids],
            }
