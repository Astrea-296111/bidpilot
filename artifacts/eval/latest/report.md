# BidPilot 实测评估

生成时间：2026-09-16T17:56:26.170475+00:00

模式：lite；模型：fake-rules-v1 (not a real LLM)；嵌入：deterministic-hash-512-v1。合成教学数据；Lite 结果不能代表真实模型泛化能力。

抽取：16 RFP / 84 条需求；Precision=1.0000，Recall=1.0000，F1=1.0000，Mandatory Recall=1.0000。

| 检索方法 | Recall@4 | Hit Rate | MRR |
|---|---:|---:|---:|
| vector | 1.0000 | 1.0000 | 0.8313 |
| bm25 | 1.0000 | 1.0000 | 0.9250 |
| hybrid | 1.0000 | 1.0000 | 0.8833 |

K 是返回 chunk 数，文档去重后计算文档级相关性和 MRR；各方法使用相同 metadata filter，禁用 query rewrite，避免把改写收益归给融合。

匹配：Accuracy=0.9750，Macro F1=0.9687。

Agent：任务完成率=1.0000，复核重试率=0.1875，引用存在率=1.0000。
平均检索次数=5.50，平均 MCP 调用次数=5.50，平均耗时=925.79 ms。

存在有效引用 ID 不等于证据蕴含结论；该指标不衡量事实正确性。平均耗时包含 MCP 子进程启动，语料与向量缓存已初始化。

## Bad cases

- M034：平台应支持 Kubernetes 与技术支持 3 年；期望 MATCH，实际 PARTIAL。检查检索过滤及复合条件。

Hybrid 相对 vector 的 Recall 差值为 +0.0000；不预设 Hybrid 一定更好。小语料、hash 嵌入和非穷举标注限制了结论。

测量范围见 summary.json；默认 Lite 不测量真实模型、BGE 或 reranker；Full 基础设施仍需另测。

下一步：补充独立真实格式数据、改写语义查询、负例与否定范围标注；在同一固定数据集上配置真实模型重跑，禁止用当前指标替代。
