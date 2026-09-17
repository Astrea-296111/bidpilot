# 评估方法、复现与 Bad Case

执行 `python -m eval.run` 或 Windows 的 `scripts/eval.ps1`。应用永远不读 eval/datasets，评测程序才读取标注。数据是人工设计规则后生成的合成教学 fixture，措辞与企业文档共享许多术语，不是独立真实业务 benchmark。

| 评测 | 数据与对齐 | 指标 |
|---|---|---|
| Requirement | 16 个 RFP，84 条；normalized text + category + mandatory 精确对齐 | Precision / Recall / F1 / 强制召回 |
| Retrieval | 40 条查询，文档级相关标注；相同类别 filter，Top 4 chunks 后按文档去重 | Recall@4 / Hit Rate / MRR |
| Match | 40 条 MATCH/PARTIAL/GAP；不让 provider 读取 expected_status | Accuracy / Macro F1 / confusion matrix |
| Agent | 16 个 RFP 运行真实图、真实 MCP 到人工确认，之后拒绝保存 | 完成率 / retry率 / 平均调用与延迟 / 引用存在率 |

Recall@K：相关文档命中数除以该条相关文档数，再对查询取平均。Hit Rate：至少命中一个相关文档的查询比例。MRR：去重后第一篇相关文档的倒数排名均值。这里 K 是 chunk 检索预算，不是恰好 K 篇唯一文档；解释指标时必须带上这个定义。

同样 metadata filter 下比较 Vector-only、BM25-only 与 Hybrid；此处不使用 query rewrite，避免混合多种收益。可选 rerank 只有真实模型加载并成功运行才可算实测；不可用不以 fallback RRF 结果冒充 rerank。

完成率表示有需求矩阵、评分、大纲并停在 HITL，不代表业务结论正确。引用存在率也不代表证据完全支持答案。平均延迟包含 MCP 子进程开销，但 embedding/索引已初始化，部分缓存会命中，不能当成冷启动 SLA。LLM 调用统计为逻辑 structured 请求数，provider 内部重试可能产生更多 HTTP 请求；tool_calls 含失败尝试，重检最多一次。

## 真实结果

完整机器可读结果在 `artifacts/eval/latest/summary.json`，保留模型名、操作系统、Python 版本、数据集 SHA256；逐条检索结果在 `artifacts/eval/retrieval_results.csv`。同目录 `match_results.json`、`extraction_results.json`、`agent_results.json` 可定位问题。

本次 Lite 匹配 Accuracy=0.975，Macro F1≈0.9687。三种检索 Recall@4 都是 1.0，MRR：Vector≈0.8313、BM25=0.9250、Hybrid≈0.8833。所以不能宣传 Hybrid 在该数据上全面优于 BM25。抽取 F1=1.0 是规则型 bullet fixture 的结果，不是任意 RFP 理解效果。

M034 同时要求 Kubernetes 和 3 年服务，technical filter 漏掉 services 文档，因此从 MATCH 标注退成 PARTIAL。见 report.md。样本太小、任务容易、规则与语料同域、标注不穷举所有有效 evidence，均限制结论。

## 使用真实模型

先完成 Full 的 API/模型与 Qdrant 配置，再执行 `python -m eval.run --mode full`，可选 `--rerank`。会产生 API 调用费用。评测仍用隔离 SQLite 记录业务数据，创建临时 Qdrant collection，避免改正式 collection；所以它不等同于 PostgreSQL/Redis/Compose 的系统集成验收。

建议保留固定数据，不在调参时不断改标签；新增真实格式的独立测试集、跨页表格、否定/范围/时间条件和无答案问题。先比较召回，再比较判断能力，最后测图任务。LLM-as-Judge 只能辅助，可能与生成模型共享偏差；关键资质需要人工原文核验。
