import argparse
import asyncio
import csv
import hashlib
import json
import platform
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from bidpilot.config import Settings
from bidpilot.service import BidPilotService
from eval import agent_eval, match_eval, requirement_eval, retrieval_eval


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


async def run(mode="lite", rerank=False):
    root = Path(__file__).resolve().parents[1]
    output = root / "artifacts/eval/latest"
    datasets = {
        name: json.loads((root / f"eval/datasets/{name}.json").read_text(encoding="utf-8"))
        for name in ["extraction", "retrieval", "matching"]
    }
    with tempfile.TemporaryDirectory(prefix="bidpilot-eval-") as temp:
        overrides = {"embedding_provider": "hash"} if mode == "lite" else {}
        settings = Settings(
            _env_file=None if mode == "lite" else ".env",
            mode=mode,
            project_root=root,
            runtime_dir=Path(temp),
            database_url="sqlite+aiosqlite:///" + (Path(temp) / "eval.db").as_posix(),
            enable_reranker=rerank,
            qdrant_collection="bidpilot_eval_" + uuid4().hex,
            **overrides,
        )
        async with BidPilotService(settings) as service:
            extraction, ext_rows = await requirement_eval.evaluate(
                service.llm, root, datasets["extraction"]
            )
            retrieval, ret_rows = await retrieval_eval.evaluate(service.rag, datasets["retrieval"])
            matching, match_rows = await match_eval.evaluate(
                service.llm, service.rag, datasets["matching"]
            )
            paths = sorted((root / "data/rfps").glob("*.md"))
            agent, agent_rows = await agent_eval.evaluate(service, paths)
            summary = {
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "mode": mode,
                "model": service.llm.model_name,
                "embedding": service.rag.embedding.name,
                "environment": {"python": platform.python_version(), "platform": platform.system()},
                "dataset_sha256": {
                    n: hashlib.sha256((root / f"eval/datasets/{n}.json").read_bytes()).hexdigest()
                    for n in datasets
                },
                "extraction": extraction,
                "retrieval": retrieval,
                "matching": matching,
                "agent": agent,
                "full_mode": "NOT_MEASURED (eval uses isolated SQLite even with a real model)",
                "semantic_embedding": "MEASURED" if mode == "full" else "NOT_MEASURED",
                "limitation": "Synthetic fixtures; Lite rules do not measure real LLM quality.",
            }
            if service.rag.reranker.warning:
                summary["retrieval"]["rerank"] = "NOT_MEASURED: " + service.rag.reranker.warning
            if mode == "full" and service.rag.vector_ready:
                service.rag.vector.client.delete_collection(settings.qdrant_collection)
    dump(output / "summary.json", summary)
    dump(output / "extraction_results.json", ext_rows)
    dump(output / "match_results.json", match_rows)
    dump(output / "agent_results.json", agent_rows)
    dump(root / "artifacts/eval/retrieval_summary.json", retrieval)
    csv_path = root / "artifacts/eval/retrieval_results.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(ret_rows[0]))
        writer.writeheader()
        writer.writerows(ret_rows)
    lines = [
        "# BidPilot 实测评估",
        "",
        f"生成时间：{summary['generated_at']}",
        "",
        f"模式：{mode}；模型：{summary['model']}；嵌入：{summary['embedding']}。合成教学数据；Lite 结果不能代表真实模型泛化能力。",
        "",
        f"抽取：{extraction['rfps']} RFP / {extraction['gold_requirements']} 条需求；Precision={extraction['precision']:.4f}，Recall={extraction['recall']:.4f}，F1={extraction['f1']:.4f}，Mandatory Recall={extraction['mandatory_recall']:.4f}。",
        "",
        "| 检索方法 | Recall@4 | Hit Rate | MRR |",
        "|---|---:|---:|---:|",
    ]
    for mode in ["vector", "bm25", "hybrid"]:
        r = retrieval[mode]
        lines.append(f"| {mode} | {r['recall_at_k']:.4f} | {r['hit_rate']:.4f} | {r['mrr']:.4f} |")
    lines += [
        "",
        "K 是返回 chunk 数，文档去重后计算文档级相关性和 MRR；各方法使用相同 metadata filter，禁用 query rewrite，避免把改写收益归给融合。",
        "",
        f"匹配：Accuracy={matching['accuracy']:.4f}，Macro F1={matching['macro_f1']:.4f}。",
        "",
        f"Agent：任务完成率={agent['task_success_rate']:.4f}，复核重试率={agent['reviewer_retry_rate']:.4f}，引用存在率={agent['citation_validity_rate']:.4f}。",
        f"平均检索次数={agent['average_retrieval_calls']:.2f}，平均 MCP 调用次数={agent['average_tool_calls']:.2f}，平均耗时={agent['average_latency_ms']:.2f} ms。",
        "",
        "存在有效引用 ID 不等于证据蕴含结论；该指标不衡量事实正确性。平均耗时包含 MCP 子进程启动，语料与向量缓存已初始化。",
        "",
        "## Bad cases",
        "",
    ]
    for r in match_rows:
        if r["expected"] != r["predicted"]:
            lines.append(
                f"- {r['id']}：{r['text']}；期望 {r['expected']}，实际 {r['predicted']}。检查检索过滤及复合条件。"
            )
    for r in ret_rows:
        if r["mode"] == "hybrid" and r["recall_at_k"] < 1:
            lines.append(
                f"- {r['id']} Hybrid 漏召回：{r['query']}；期望 {r['expected_docs']}，召回 {r['retrieved_docs']}。"
            )
    delta = retrieval["hybrid"]["recall_at_k"] - retrieval["vector"]["recall_at_k"]
    lines += [
        "",
        f"Hybrid 相对 vector 的 Recall 差值为 {delta:+.4f}；不预设 Hybrid 一定更好。小语料、hash 嵌入和非穷举标注限制了结论。",
        "",
        "测量范围见 summary.json；默认 Lite 不测量真实模型、BGE 或 reranker；Full 基础设施仍需另测。",
        "",
        "下一步：补充独立真实格式数据、改写语义查询、负例与否定范围标注；在同一固定数据集上配置真实模型重跑，禁止用当前指标替代。",
    ]
    (output / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["lite", "full"], default="lite")
    parser.add_argument("--rerank", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.mode, args.rerank))
