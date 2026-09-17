# PROJECT GUIDE：从一点 Python 到讲懂 BidPilot

先跑 README 的 Lite 命令，再对照本指南读真实代码。看到 “模拟” 不代表框架是假的：LangGraph、Qdrant、MCP、数据库和 HTTP 都是真实运行的，只有企业资料与 Lite 的语言判断/嵌入是教学替身。

## 开始前只需认识四件事

函数接收输入并返回结果；字典按 key 保存数据；类把数据/行为组织在一起；await 表示等待可让出执行权的操作。不必先背完 Agent 术语。打开 src/bidpilot/cli.py，从 demo 函数进入 service.analyze，跟着一次真实调用读。

## 1. 业务闭环

客户说“必须支持 Kubernetes”，不是问你 Kubernetes 是什么。你需要找公司资料，确认是否有这项能力；如果同时要求五年服务而公司只有三年，就应标出差距。BidPilot 把每一条要求、能力、证据和评分连接起来，最后给人复核。

代码位置：`src/bidpilot/service.py:BidPilotService.analyze`。

## 2. 一次 RFP 如何流转

先上传文件并生成 tender_id。解析器把正文分成有来源的 sections；Analyst 生成 Requirement；Matcher 为每一条检索；Reviewer 检查引用与结论；score 计算分数；outline 组织应答章节。human_review 暂停，Approve 后才调用 MCP 写机会。

代码位置：`src/bidpilot/api/app.py:create_app；src/bidpilot/agent/nodes.py`。

## 3. LangChain

LangChain 提供模型和文档处理组件，像积木。本项目真实使用 ChatOpenAI.with_structured_output 以及 RecursiveCharacterTextSplitter。它们解决“怎么调用一个模型或切一段文档”，不决定整项业务该走哪一步。

代码位置：`src/bidpilot/llm/openai_compatible.py；src/bidpilot/rag/chunker.py`。

## 4. LangGraph

LangGraph 描述有状态、可分支、可恢复的工作流。本项目只有一个业务图；三个 Agent 是图中的职责节点，不是互相无限聊天的机器人。FakeLLM 也经过同一张真实图，因此不依赖付费 API 就能学习图运行。

代码位置：`src/bidpilot/agent/graph.py:build_graph`。

## 5. State

State 是当前任务随身携带的资料袋，里面有需求、证据、已做的工具调用、重试次数和决策。节点返回一个字典，只更新它负责的字段。了解这个结构比背框架函数更重要。

代码位置：`src/bidpilot/agent/state.py:BidState`。

## 6. Node

Node 是一个步骤，例如 parse 读文件、analyst 抽需求、score 做算术。输入是旧 State，返回更新。把步骤拆开，才能知道失败发生在抽取、检索还是判断，也便于用测试分别验证。

代码位置：`src/bidpilot/agent/nodes.py:AgentNodes`。

## 7. Edge 与 Conditional Edge

普通边规定下一步；条件边在多个路径中选一个。本项目每个步骤回到 supervisor，supervisor 按 phase 选路。Reviewer 认为证据不足时把 phase 设为 matcher，从而发生一次重检。

代码位置：`src/bidpilot/agent/graph.py:builder.add_conditional_edges`。

## 8. Supervisor Pattern

Supervisor 像受限的任务调度员，决定分析现在在哪一阶段。这里不用模型自由决定下一步，只读 phase 和预算。这让状态迁移容易审计，并避免模型不断调用工具消耗预算。

代码位置：`src/bidpilot/agent/nodes.py:supervisor`。

## 9. Checkpoint

Checkpoint 把每一步状态写到磁盘。如果应用在人工确认前关闭，重新启动还知道做到哪里。thread_id 就像这份任务的存档号，换号会创建新流程。它与最终业务报告表用途不同。

代码位置：`src/bidpilot/service.py:__aenter__ / config`。

## 10. ReAct / Tool Calling

这里采用有限的“规划→行动→观察→回答”：QueryPlan 决定搜索词和只读工具，MCP 执行，Matcher 根据 observation 与证据输出匹配。没有展示私有链式思考，也没有任意次数的模型自循环。Lite 的规划来自规则，Full 的规划来自模型结构化输出。

代码位置：`src/bidpilot/agent/nodes.py:matcher / tool_arguments`。

## 11. Structured Output

模型需要返回符合 Pydantic schema 的对象，而不是一段看起来像 JSON 的文本再用正则猜。QueryPlan 最多两个查询，confidence 必须在 0 到 1，状态只能三个固定值。校验失败会触发一次请求重试。规则可以约束形状，但不能保证事实正确。

代码位置：`src/bidpilot/agent/schemas.py；src/bidpilot/llm/openai_compatible.py:structured`。

## 12. Multi-Agent

一个 Agent 只做抽取，一个做检索与匹配，另一个独立复核。它们的输入、标准和 prompt 不同，即使调用同一个模型仍然是不同职责。拆分能减少上下文混杂，但增加调用数量，因此只设三个。

代码位置：`src/bidpilot/agent/prompts/；src/bidpilot/agent/nodes.py`。

## 13. Reflection / Reviewer

Reviewer 重新检查 Matcher 的结果，例如“ISO20000 没有证据却写 MATCH”。先用 Python 检查引用 ID 归属，再用独立判断检查文本支持。最多一次重检；仍有问题保守改成 GAP，不把“重试过”当作“已正确”。

代码位置：`src/bidpilot/agent/nodes.py:reviewer`。

## 14. Human-in-the-loop

模型读资料不需要每次打断人，但写入投标机会会改变业务状态，所以图先展示具体项目、分数和建议。用户明确同意后 resume。拒绝结束而不写入，这一点有自动测试覆盖。

代码位置：`src/bidpilot/agent/nodes.py:human_review / save`。

## 15. 短期 Memory 与上下文管理

当前招标上下文在 graph checkpoint；聊天历史在 ChatMemory，最多最近四轮。每条需求仅拿少量 evidence，Reviewer 按四条一批处理。这样避免把整本标书、全部知识库和所有聊天都塞给模型。

代码位置：`src/bidpilot/service.py:chat；src/bidpilot/agent/nodes.py:analyst / reviewer`。

## 16. RAG

RAG 是先查资料再生成结论。这里查的是企业知识，回答的是“公司能否满足这一条招标要求”。如果查不到，不让模型凭常识猜公司有证书；必须保守标缺口，并让人补充资料。

代码位置：`src/bidpilot/rag/pipeline.py:RAGPipeline`。

## 17. Chunk

整本手册直接检索粒度太粗，要切成片段。默认 500 字符一块，块间保留 80 字符，减少一句话刚好被切断。每个 chunk 带 document_id、category、source、chunk_index、updated_at 与 tags。

代码位置：`src/bidpilot/rag/chunker.py:chunk_document`。

## 18. Embedding

Embedding 把文本变成一个数字向量，让意思接近的句子有机会相近。Full 默认小型中文 BGE，也可用 API；Lite 为避免下载，用词项哈希向量。哈希向量是流程基线，不会真的理解同义词。

代码位置：`src/bidpilot/rag/embeddings.py:EmbeddingProvider / create_embedding`。

## 19. Vector Search 与 Cosine

向量检索在向量空间找相近的 chunk。Cosine 比较方向，对已归一化向量可理解为点积；分数接近不代表满足所有数值/否定条件。还需要后面的证据核对。

代码位置：`src/bidpilot/rag/vector_store.py:search`。

## 20. Qdrant

Qdrant 专门存储和查询向量，附带 metadata payload。Lite 在本机目录运行，无需 Docker；Full 连接 Qdrant Server。它不替代存储招标业务关系的 PostgreSQL。

代码位置：`src/bidpilot/rag/vector_store.py:CompanyKnowledgeVectorStore`。

## 21. BM25

BM25 擅长找精确词，例如 ISO27001、RTO、99.95%。如果只用语义向量，有时会把两个看起来相近但数字不同的条件混在一起。中文在这个小项目里用字和双字片段，不需额外分词模型。

代码位置：`src/bidpilot/rag/bm25.py:tokenize / BM25Index`。

## 22. Hybrid Retrieval 与 RRF

Hybrid 同时拿向量和 BM25 的候选。因为两种分数量纲不同，RRF 不直接加原始分数，而按名次给 1/(60+rank)，多路靠前的文档总分更高。融合有收益也有噪声，必须对照评测。

代码位置：`src/bidpilot/rag/rrf.py:reciprocal_rank_fusion`。

## 23. Rerank

Reranker 重新细看 query 和候选文本是否相关，比向量的独立编码更细致但计算更贵。因此只处理 RRF 的前 8 个，而不是整个知识库。默认关闭，缺少模型时保留 RRF 顺序并记警告。

代码位置：`src/bidpilot/rag/reranker.py:Reranker.rank`。

## 24. Metadata Filter

资质需求优先只看 certifications/company，这通常能减少噪声。但“部署并支持三年”同时涉及 technical 和 services，过硬的筛选也会漏掉资料。评测里的 M034 就展示了这个问题。

代码位置：`src/bidpilot/rag/pipeline.py:CATEGORY_FILTER`。

## 25. Query Rewrite

原始条款可能有许多公文词语，改写成短查询更适合检索。复合要求最多拆成两条，并保留数字/单位。改写也可能丢条件，因此结果仍要对原始 requirement 校验。

代码位置：`src/bidpilot/agent/nodes.py:matcher；src/bidpilot/agent/prompts/query_rewrite.md`。

## 26. Citation 与 Grounded Answer

Citation 是能回到原始 chunk 的 evidence_id，不是模型编的文献编号。Reviewer 检查引用是否来自当前需求的检索集合；报告保存原文快照。来源真实和结论正确是两件事，后者仍需文本蕴含核对。

代码位置：`src/bidpilot/agent/nodes.py:reviewer；src/bidpilot/persistence/repository.py:save_report`。

## 27. MCP

MCP 规定应用怎样发现和调用工具。Server 暴露六个企业工具，Client 通过协议调用。stdio 用子进程输入输出，HTTP 用网络连接。它不是“把 Python 函数名字叫作 tool”这么简单。

代码位置：`mcp_server/bidpilot_mcp/server.py；src/bidpilot/mcp_client/client.py`。

## 28. FastAPI

FastAPI 把 Python 函数暴露为 HTTP 接口，并用 Pydantic 做输入校验。上传接口接收 multipart 文件，report 接口返回 JSON。访问 /docs 可以交互式试接口，比一开始就看 UI 更容易排查问题。

代码位置：`src/bidpilot/api/app.py:create_app`。

## 29. asyncio / async

等待数据库、模型和网络时，async 可以把控制权还给事件循环，处理其他请求。但给 CPU 任务加 async 不会自动变快；本项目把同步 embedding 和 Qdrant 操作放进 to_thread。并发仍受任务锁和单 worker 边界约束。

代码位置：`src/bidpilot/service.py；src/bidpilot/rag/pipeline.py:retrieve`。

## 30. SSE

SSE 是服务端向浏览器持续发送文本事件。分析任务只需进度向客户端流动，比双向 WebSocket 简单。节点、进度、检索、复核、结果分别有 event 类型；支持 Last-Event-ID 在同进程内续读。

代码位置：`src/bidpilot/service.py:stream_events；src/bidpilot/api/app.py:stream`。

## 31. SQLAlchemy 与 PostgreSQL

SQLAlchemy 把 Python 对象映射成表并管理事务。SQLite 方便本地入门；PostgreSQL 适合多连接和持久业务数据。表有外键，把 tender、requirement、match、evidence 串起来，写报告时同一个事务提交。

代码位置：`src/bidpilot/persistence/models.py；src/bidpilot/persistence/repository.py`。

## 32. Redis 与 Cache

重复查询可以复用结果，默认 TTL 300 秒；分析状态也有缓存；POST 使用计数器限流。Redis 多进程可共享，Lite 用 MemoryCache。Redis 故障时本进程回退，不能再声称跨节点限流有效。

代码位置：`src/bidpilot/cache/store.py`。

## 33. Docker Compose

Compose 一次启动 Postgres、Redis、Qdrant、backend、MCP Server，方便统一服务地址和持久卷。宿主 Windows 只需 Docker Desktop 和 PowerShell 命令。UI 可在宿主运行，不引入 Kubernetes。

代码位置：`docker-compose.yml；Dockerfile`。

## 34. Eval

测试关注代码是否满足约束，评测关注系统表现。例如 pytest 验证“拒绝不写入”，Eval 比较“Hybrid 的召回是否更好”。两者不可替代。本次合成数据中 BM25 的 MRR 更高，所以保留这个结果。

代码位置：`eval/run.py；eval/requirement_eval.py；eval/retrieval_eval.py；eval/match_eval.py；eval/agent_eval.py`。

## 35. 确定性评分

MATCH=1，PARTIAL=0.5，GAP=0，再按维度和原文权重加权。关键资质缺口能直接 NO_BID。模型可以解释资料，但算术和否决规则由 Python 实现，便于版本控制与测试。

代码位置：`src/bidpilot/matching/scoring.py；config/scoring.yaml`。

## 36. 错误预算

一次模型请求最多两次尝试，图最多 30 steps，重检最多一次，MCP 最多 10 次并为确认写入留名额。失败时有明确状态和 warning，不靠无限重试掩盖服务故障。

代码位置：`src/bidpilot/config.py；src/bidpilot/llm/openai_compatible.py；src/bidpilot/agent/nodes.py`。

## 按五次练习掌握项目

1. 运行银行 PDF。打开 JSON report，找一条 requirement_id，沿 matches.evidence_ids 找到 evidence 原文；解释为何它支持结论。
2. 运行资质缺失 RFP。确认没有公司资料就不能猜有 ISO20000；观察 retry_count 和最终 NO_BID。
3. 阅读 rrf.py，用两份排名手算一个文档的 RRF 分数，再看 retrieval_results.csv。说明为什么 BM25 在小语料上反而更好。
4. 在人工确认处停止后重启 backend，用原 tender_id 审批。运行 checkpoint 集成测试，确认是磁盘恢复。
5. 打开 tests 中伪造 citation、数字阈值、审批拒绝测试。选择一项修改需求再运行，说明失败发生在哪一层。

## 常见启动问题

找不到 py：安装 Python 3.11/3.12 并勾选 launcher。脚本被禁用：使用 README 的进程级策略或直接 python 命令。Qdrant 目录锁：关闭另一个使用同 runtime 的 backend，或给第二个进程不同 RUNTIME_DIR。扫描 PDF 无文字：先 OCR，本项目不会编造正文。Full 启动缺模型：setup.ps1 -Models 或 API embedding；模型下载失败会降级并在 health/report 提示。Docker 访问失败：先看 docker compose logs backend，核对 LLM Key、共享 secret、服务健康和本地模型下载。

API 返回 429：演示默认同一 socket peer 每分钟 20 次 POST，稍后重试或在开发环境调 RATE_LIMIT。企业代理使用 SOCKS 时依赖包含 httpx[socks]；对本机服务配置 NO_PROXY=localhost,127.0.0.1。不要把 Key 写进简历、日志或截图。

## 面试前自查

能画业务顺序，能找到三个 prompt，能解释一条 evidence 的来源，能手算一个评分，能演示 interrupt/resume，能说出至少一个坏例，并能区分“代码支持”和“当前环境实际测过”。先做到这些，再阅读 docs/interview-guide.md 的深入追问。
