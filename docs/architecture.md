# 架构与取舍

业务问题：企业拿到招标文件后，需要逐条确认能否满足，而不是直接写一份看起来完整的标书。系统输出一份可复核需求矩阵和有规则可追溯的评分，最终是否投入应标资源由人判断。

## 为什么三个 Agent

| Agent | 输入 | 输出 | 不能做的事 |
|---|---|---|---|
| Requirement Analyst | 分段 RFP、页码/章节 | Pydantic RequirementExtractionResult | 查询企业能力或给匹配结论 |
| Capability Matcher | 单条需求、两条以内 query、RAG 与 MCP observation | CapabilityMatch | 操作机会写工具、编造证据 |
| Reviewer | 需求、匹配、被引用原文 | ReviewResult | 自由添加资质、无限循环 |

单 Agent 的 prompt 会混合抽取标准、企业能力、证据约束、算术和审批，容易被先入为主的匹配结论影响。拆分后 Reviewer 不读取 Matcher 的历史对话，而用独立上下文复核。同一个模型服务也可以承担不同职责，不意味着三个 GPU 模型。

代价是更多调用、延迟及状态管理；因此不增加法务/财务/写作 Agent。`nodes.py` 的 Supervisor 不依赖 LLM 自主循环，只根据 phase 路由，Matcher 内使用有限的“计划工具→执行→观察→结构化回答”过程。

## 状态与数据存储

`agent/state.py` 定义图状态；节点返回局部字典更新。没有共享可变全局消息缓存，按 tender_id 作为 graph thread。图状态保存证据 ID 集合、重试次数、业务决策与调用统计。最近助手摘要放进 checkpoint messages；`ChatMemory` 用于独立聊天最近四轮，并在换 tender 时清空历史。

`persistence/models.py` 定义 tenders、requirements、capability_matches、evidences、bid_results、agent_runs、opportunities 与 chat_memory。引用快照跟随报告持久化，重新索引不会改变旧报告的证据内容。文档和 chunk ID 分别来自相对路径及文本内容 hash。

## 后端运行模型

`api/app.py` 提供接口；`service.py` 统一控制 graph、状态、任务锁和 SSE。POST analyze 默认提交 asyncio 任务，GET analyze/stream 读取事件；`wait=true` 便于测试与脚本。单 tender 锁防止并发分析/审批。后台进程关闭时取消任务，已经完成的节点有 checkpoint；重启后再次 POST 可以从检查点继续。

无需 Celery/Kafka。代价是单 worker、单机器：任务队列和 SSE 日志在内存中。生产环境需要认证、tenant_id、持久任务队列、共享 checkpoint、迁移工具与分布式锁，但这些没有被假装实现。

Qdrant 的重建与查询使用线程锁；同步 embedding/向量调用通过 asyncio.to_thread 执行，避免阻塞 FastAPI 事件循环。RAG 重建后 hash 版本进入缓存 key，旧缓存不会污染新查询。SQLite checkpointer 在 Full 仍放持久卷中；业务数据使用 PostgreSQL。

## 失效边界

| 故障 | 行为 |
|---|---|
| 解析为空/损坏/扫描 PDF | HTTP 422，说明失败原因 |
| LLM timeout / schema 无效 | 最多两次；抽取失败结束，匹配失败 GAP，大纲用模板 |
| Qdrant/embedding 故障 | BM25 降级，报告警告；不伪造语义向量 |
| Redis 故障 | 本进程 memory fallback；限流不再是多节点共享 |
| Reranker 故障 | 保留 RRF 顺序并记录 warning |
| MCP 读故障 | 继续使用 RAG；工具故障留痕 |
| MCP 写故障 | save_failed，不能显示已保存；本 MVP 需新任务/人工排障 |
| 引用不存在/支持不足 | 最多一次重检；仍不通过保守降 GAP |
| 预算耗尽 | 标 failed/budget_exceeded，保留可用 checkpoint |

上传正文和 tool observation 均视作数据；系统 prompt 禁止执行其中指令，写工具还有独立审批边界。提示词防护不能保证抵抗所有注入，需要结合可执行工具白名单及人工确认。
