# BidPilot 高频面试题

共 62 题。先说30秒核心回答，再结合代码回答追问；不要背不存在的生产指标。下面代码路径以 src/bidpilot 为基准，外部文件使用相对路径。

## 1. 为什么选 LangGraph？

**30 秒回答：** 业务既有条件分支又有暂停恢复：证据不足重检、人工同意后才保存。显式状态图比一段长链或自由循环容易测试与追踪。

**深入追问：** 如果只有一次检索问答，用简单链是否更合适？是，图会增加管理成本。

**代码位置：** `agent/graph.py`。

## 2. LangGraph 与 LangChain 的区别？

**30 秒回答：** LangChain 提供模型、文档等组件；LangGraph 负责有状态编排。本项目 splitter 与 structured output 用 LangChain，阶段/分支/checkpoint 用 LangGraph。

**深入追问：** 替换一个 LLM provider 是否必须重写图？不必，遵守统一接口即可。

**代码位置：** `llm/base.py；agent/graph.py`。

## 3. StateGraph 是什么？

**30 秒回答：** 它是按状态 schema 定义的数据流图。节点读 State 返回局部更新，再按边流转。BidState 显式保存需求、证据、重试和决策。

**深入追问：** 并发节点写同一字段怎么办？本版顺序图避免冲突；并发时需要 reducer 与冲突语义。

**代码位置：** `agent/state.py`。

## 4. Node 和 Edge 分别做什么？

**30 秒回答：** Node 执行业务工作，Edge 决定下一步。本版每个业务节点回到 supervisor，再根据 phase 路由。

**深入追问：** 为什么不让节点直接相互调用？会绕过图的状态记录与可观察性。

**代码位置：** `agent/graph.py`。

## 5. Conditional Edge 怎么用？

**30 秒回答：** supervisor 读取 phase。Reviewer 需要重试时返回 matcher，否则进入 score，路由完全受预算约束。

**深入追问：** 模型生成不存在的节点名怎么办？本版 phase 由代码设置。

**代码位置：** `agent/nodes.py:reviewer`。

## 6. Checkpoint 存什么？

**30 秒回答：** 保存图状态与执行位置，按 tender_id 做 thread_id。最终报告另存在业务表，二者职责不同。

**深入追问：** 进程崩溃后会自动调度吗？本版需要再次 POST analyze 触发恢复。

**代码位置：** `service.py:config / analyze`。

## 7. interrupt/resume 怎样保证不提前写？

**30 秒回答：** human_review 先 interrupt，save 在独立节点。Approve 后同 thread_id 恢复，才生成签名并调用写工具。

**深入追问：** 中断节点恢复时会重跑吗？会，因此 interrupt 前不能放有副作用的业务写入。

**代码位置：** `agent/nodes.py:human_review / save`。

## 8. LangGraph 怎样流式输出？

**30 秒回答：** service 消费 astream 的 updates 与 custom；节点用 writer 发布检索和进度，再转为 SSE event。

**深入追问：** 这是模型原生 token 流吗？分析是节点事件；聊天是校验后分块展示。

**代码位置：** `service.py:analyze / stream_events`。

## 9. 如何防止 Agent 死循环？

**30 秒回答：** 固定阶段路由、最多一次重检、graph steps 和工具预算共同约束，耗尽时留失败状态。

**深入追问：** 调用次数与图步骤相同吗？不同，matcher 一个节点可能处理多条需求。

**代码位置：** `config.py；agent/nodes.py:supervisor`。

## 10. 为什么不用 CrewAI？

**30 秒回答：** 这里最需要可控状态迁移和原生中断恢复，LangGraph 更贴合当前实现目标；不是认为其他框架无法实现。

**深入追问：** 如何比较框架？以可恢复、可测试、依赖成本和团队熟悉度判断。

**代码位置：** `agent/graph.py`。

## 11. 三个 Agent 怎样通信？

**30 秒回答：** 通过同一 BidState 传结构化需求、匹配与复核结果，不互相传整段聊天，也不共享不可控长期上下文。

**深入追问：** 大文档怎么防 context 污染？按段抽取、每需求取少量证据、复核分批。

**代码位置：** `agent/state.py；agent/nodes.py`。

## 12. ReAct 在哪里？

**30 秒回答：** Matcher 先输出 QueryPlan，执行检索与 MCP，再把 observation 交给结构化匹配判断。是有限规划-行动-观察流程。

**深入追问：** FakeLLM 算自主推理吗？不是，它是明确规则；真实选择在 Full provider。

**代码位置：** `agent/nodes.py:matcher`。

## 13. RAG 的完整流程是什么？

**30 秒回答：** 解析、分块、embedding、索引、改写查询、双路召回、RRF、可选 rerank、基于证据匹配、引用复核。

**深入追问：** 哪一阶段最先诊断？先看是否检索到正确证据，再看模型判断。

**代码位置：** `rag/pipeline.py`。

## 14. Chunk size 如何选？

**30 秒回答：** 默认 500 字符是兼顾条款完整与精细检索的起点，未声称最优。应在固定测试集上比较召回和上下文成本。

**深入追问：** 长表格怎么办？目前解析有限，未来按表格/章节结构切分。

**代码位置：** `rag/chunker.py`。

## 15. Overlap 有什么作用？

**30 秒回答：** 块间重复 80 字符减少跨边界丢条件，但增加存储和重复召回，需要去重和候选控制。

**深入追问：** 为什么不能无限增大？会让候选高度重复，挤走不同证据。

**代码位置：** `rag/chunker.py`。

## 16. Embedding 是什么？

**30 秒回答：** 把文本编码为向量。Full BGE 提供语义表示，Lite hash 只做确定性词项映射，不能混称真实语义模型。

**深入追问：** 换模型要做什么？重建同维度索引并更换缓存 namespace。

**代码位置：** `rag/embeddings.py`。

## 17. 为什么用 Qdrant？

**30 秒回答：** 它同时提供 Local 与 Server，方便 Windows 无 Docker 演示和 Full 迁移，还有 payload filter。

**深入追问：** 为什么不用 FAISS？本题需要同一客户端覆盖本地和服务化元数据过滤。

**代码位置：** `rag/vector_store.py`。

## 18. Cosine Similarity 有什么限制？

**30 秒回答：** 它比较向量方向，不能证明逻辑蕴含。99.95% 与99.99% 文本相似但可能不合格，所以另做数值校验。

**深入追问：** 向量距离能作为 confidence 吗？不能直接当作业务置信度。

**代码位置：** `rag/vector_store.py；matching/support.py`。

## 19. BM25 为什么适合招投标？

**30 秒回答：** 精确证书名、参数和数值很多，关键词匹配有价值。本次小数据集上 BM25 的 MRR 确实优于 Hybrid。

**深入追问：** 中文怎么分词？当前字/双字和英文技术词，生产可比较专业分词器。

**代码位置：** `rag/bm25.py`。

## 20. Hybrid 是怎么做的？

**30 秒回答：** 向量和 BM25 各取 10，RRF 合并到8，再输出4或重排。两路兼顾语义相近和词项精确。

**深入追问：** 它一定优于单路吗？不，融合也会带入噪声，要比较真实结果。

**代码位置：** `rag/pipeline.py:search_sync`。

## 21. RRF 公式怎样解释？

**30 秒回答：** 每路按名次加 1/(60+rank)，多路都靠前就更高。不要求两个检索器原始分数可比。

**深入追问：** k 越大有何影响？名次差异被压平，需要通过固定评测比较。

**代码位置：** `rag/rrf.py`。

## 22. Rerank 与向量检索差别？

**30 秒回答：** 向量独立编码适合大规模召回；CrossEncoder 同时看 query/document，更细但更贵，所以只重排少量候选。

**深入追问：** 本次测到效果了吗？没有，默认关闭，NOT_MEASURED。

**代码位置：** `rag/reranker.py`。

## 23. Metadata Filter 有什么副作用？

**30 秒回答：** 减少噪声也可能排除正确证据。M034 技术与服务复合需求就因分类漏召回；重试可放宽，但不是保证。

**深入追问：** 怎么改进？给子查询独立分类或用 soft boost 代替硬过滤。

**代码位置：** `rag/pipeline.py:CATEGORY_FILTER`。

## 24. Query Rewrite 如何避免丢条件？

**30 秒回答：** 保留证书、数值、单位；最多两条 query；最终仍按原始 requirement 判断，而不是按改写后的短词判断。

**深入追问：** 怎么测 rewrite？在同一召回方法上单独做开关实验，别把收益混入 RRF。

**代码位置：** `agent/prompts/query_rewrite.md`。

## 25. Recall@K 怎么定义？

**30 秒回答：** 每条查询命中的相关文档数除以标注相关文档数，再平均。本版 K 指返回4个 chunks，去重后做文档级统计。

**深入追问：** 标注不全怎么办？会低估等价证据，要补充人工相关性判断。

**代码位置：** `../../eval/retrieval_eval.py`。

## 26. MRR 怎么定义？

**30 秒回答：** 每条查询第一个相关文档的倒数排名均值，更关注正确证据是否靠前。

**深入追问：** 它会奖励找到多个证据吗？不会，因此还看 Recall。

**代码位置：** `../../eval/retrieval_eval.py`。

## 27. RAG 怎样防幻觉？

**30 秒回答：** 限定证据上下文、缺证据用 GAP、引用归属检查、独立 Reviewer，失败重检后保守处理。没有单一措施保证零幻觉。

**深入追问：** 资料本身错怎么办？来源真实不代表内容正确，仍需治理与人工核实。

**代码位置：** `agent/nodes.py:reviewer`。

## 28. 如何保证 citation 真实？

**30 秒回答：** ID 来自实际 chunk；匹配引用必须属于该条需求检索集合；持久化保存原文快照。

**深入追问：** 引用存在是否等于支持结论？不是，还要看否定、条件、数值和范围。

**代码位置：** `agent/nodes.py:reviewer；persistence/repository.py`。

## 29. 什么时候使用 RAG，什么时候用 Tool？

**30 秒回答：** 长手册/案例适合 RAG 找片段；精确证书登记或机会保存适合结构化工具。工具 observation 不能替代文档 MATCH 证据。

**深入追问：** 工具结果如何做引用？本版只作辅助上下文，不冒充文档 citation。

**代码位置：** `agent/nodes.py:matcher`。

## 30. MCP 是什么？

**30 秒回答：** 它是模型应用与工具服务之间的标准发现和调用协议；包含客户端、服务端和传输。

**深入追问：** MCP 自己会决定调用哪个工具吗？不会，规划由模型/应用决定。

**代码位置：** `mcp_client/client.py`。

## 31. MCP Client 和 Server 分别在哪？

**30 秒回答：** Client 在 mcp_client，用 ClientSession initialize/call_tool；Server 在独立包，用官方 FastMCP 暴露六工具。

**深入追问：** 怎么证明不是直接函数调用？集成测试实际启动子进程与 HTTP 服务。

**代码位置：** `mcp_client/client.py；../../mcp_server/bidpilot_mcp/server.py`。

## 32. 什么是 MCP Tool？

**30 秒回答：** 一个有名称、说明、输入 schema 和返回结构的可调用能力。读和写有不同权限边界。

**深入追问：** 参数错误怎么办？SDK/schema 及服务端校验返回错误，客户端不假装成功。

**代码位置：** `../../mcp_server/bidpilot_mcp/server.py`。

## 33. stdio 适合什么场景？

**30 秒回答：** 同机客户端启动子进程，标准输入输出传协议，部署最简单且无监听端口。日志必须走 stderr。

**深入追问：** Windows 有什么注意？用 sys.executable、Path 和 SDK 管理进程，避免 bash 命令。

**代码位置：** `mcp_client/client.py:connect`。

## 34. Streamable HTTP 的价值？

**30 秒回答：** 客户端和工具可以分开部署，Compose backend 连接独立 mcp-server。它需要考虑连接、超时和网络认证。

**深入追问：** 当前有企业认证吗？没有，本地演示限制端口，不能直接公开。

**代码位置：** `mcp_client/client.py；../../docker-compose.yml`。

## 35. MCP 和 Function Calling 有何区别？

**30 秒回答：** Function Calling 是模型输出工具选择与参数的能力；MCP 是工具发现与执行协议。两者可以配合但不等同。

**深入追问：** 本项目怎么接？QueryPlan 受模型 schema 约束，执行使用 MCP Client。

**代码位置：** `llm/openai_compatible.py；agent/nodes.py:matcher`。

## 36. MCP 和 REST API 有何区别？

**30 秒回答：** REST 通常面向具体业务资源，MCP 提供统一工具发现与模型应用调用方式。MCP Server 内部也可调用 REST。

**深入追问：** 为什么已有 FastAPI 还用 MCP？为了独立暴露企业工具与客户端协议边界。

**代码位置：** `api/app.py；mcp_client/client.py`。

## 37. 为什么只用三个 Agent？

**30 秒回答：** 抽取、匹配、验证的输入与判断标准不同，值得拆分；更多角色会增加成本与状态复杂度，本项目没有必要。

**深入追问：** 什么时候单 Agent 更好？短任务、低风险、没有独立校验需求时。

**代码位置：** `agent/nodes.py`。

## 38. Supervisor Pattern 的代价？

**30 秒回答：** 中央路由便于控制和观察，但会成为调度中心，步骤更多。这里保持确定性以换取可解释性。

**深入追问：** 能否用 LLM supervisor？可以，但要约束 action space 和预算，本项目不用。

**代码位置：** `agent/nodes.py:supervisor`。

## 39. Reflection 如何避免自我肯定？

**30 秒回答：** Reviewer 用独立 prompt 和被引用原文，不看长篇 matcher 历史；再加确定性引用 gates。相同模型仍可能共享偏差。

**深入追问：** 更可靠方案？独立人工标注/模型交叉复核与关键资质人工审查。

**代码位置：** `agent/prompts/reviewer.md`。

## 40. Multi-Agent 有哪些缺点？

**30 秒回答：** 增加调用、延迟、状态传输、调试难度，以及错误在节点之间传播的风险；不是角色越多越聪明。

**深入追问：** 怎么判断值得拆？看责任标准是否独立、能否单独评测。

**代码位置：** `service.py；agent/nodes.py`。

## 41. 怎样控制成本？

**30 秒回答：** 单条需求上下文、最多两 query、四条 evidence、批量 Reviewer、有限 retry/工具调用，外加检索缓存。

**深入追问：** 有哪些没计入？provider 重试、模型 token 单价和下载成本，不能仅看逻辑调用数。

**代码位置：** `config.py；rag/pipeline.py`。

## 42. FastAPI async 有什么意义？

**30 秒回答：** 模型/网络/数据库等待时释放事件循环；同步 CPU/向量操作放到线程。async 本身不会加速 CPU 工作。

**深入追问：** 为什么不能在 async 中直接慢速 encode？会阻塞其他请求。

**代码位置：** `service.py；rag/pipeline.py:retrieve`。

## 43. asyncio 锁解决什么？

**30 秒回答：** 每 tender 一个锁防止同任务同时分析或确认，聊天每 thread 锁防止历史相互覆盖。

**深入追问：** 能跨进程吗？不能，当前单 worker；生产需分布式锁。

**代码位置：** `service.py`。

## 44. SSE 和 WebSocket 怎么选？

**30 秒回答：** 这里只需要服务端推分析进度，SSE 更简单并支持重连标识。WebSocket 适合真正的双向高频交互。

**深入追问：** 重启后 SSE 能完整回放吗？本版只恢复持久报告，内存节点日志会丢。

**代码位置：** `service.py:stream_events`。

## 45. Redis 用在哪三个地方？

**30 秒回答：** 检索结果缓存、分析状态、请求计数限流。Lite 用相同接口的 MemoryCache。

**深入追问：** Redis 不可用会怎样？回退本机且 health 标记降级，不能再保证多节点一致。

**代码位置：** `cache/store.py`。

## 46. PostgreSQL 存什么？

**30 秒回答：** 招标、需求、匹配、证据快照、结果、运行统计和机会，保留业务关系与事务。

**深入追问：** 当前有迁移工具吗？MVP create_all，无 Alembic；生产需要版本化迁移。

**代码位置：** `persistence/models.py；persistence/repository.py`。

## 47. PostgreSQL 和 Qdrant 的分工？

**30 秒回答：** 关系库保存业务事实与审计，Qdrant 存向量和检索 metadata，优化相似度查询。

**深入追问：** 是否重复保存 chunk？报告证据快照保留历史，检索库可重建。

**代码位置：** `persistence/models.py；rag/vector_store.py`。

## 48. 缓存如何避免索引更新后返回旧结果？

**30 秒回答：** 检索 key 包含语料 version hash、模型名、query、filter 和 mode；重建改变 version。

**深入追问：** 相同文本同名模型升级怎么办？模型版本应进入名称或手动清缓存/索引。

**代码位置：** `rag/pipeline.py:retrieve`。

## 49. API timeout 怎么处理？

**30 秒回答：** 模型有等待超时、最多两次请求；匹配失败保守 GAP，抽取不能继续则 failed。MCP 也有调用超时。

**深入追问：** UI 断开会取消任务吗？默认任务与 SSE 订阅分开，后端继续到确认点。

**代码位置：** `llm/openai_compatible.py；service.py`。

## 50. 为什么评分不用 LLM 算？

**30 秒回答：** 固定算术与否决规则应可重复、可测试、可解释。模型更适合判断证据与生成说明，不能任意更改业务阈值。

**深入追问：** 规则如何变更？改 YAML 并回归边界测试，记录版本。

**代码位置：** `matching/scoring.py`。

## 51. Mandatory 权重为什么大？

**30 秒回答：** 强制要求通常具有准入含义。除35%覆盖权重，还对 GAP 扣分并对资质缺失否决，避免总体高分掩盖不合格。

**深入追问：** 会重复计权吗？会，同时计入其业务维度，这是明确设计选择。

**代码位置：** `config.py；../../config/scoring.yaml`。

## 52. MATCH/PARTIAL/GAP 怎么定义？

**30 秒回答：** 全部条件明确有证据支持为 MATCH，相关能力但部分不足 PARTIAL，没有能力或证据为 GAP。没有检索到不能推断公司一定没有，只能标未证实。

**深入追问：** 3 年对5年服务是什么？PARTIAL，并列出2年差距/商务待确认。

**代码位置：** `matching/support.py；agent/schemas.py`。

## 53. 缺少某个评分维度怎么办？

**30 秒回答：** 不把缺失维度默认当100分，把它标 N/A 并归一化其余维度权重；零权重同样不参与。

**深入追问：** 是否所有 RFP 分数可以直接横比？不能，适用需求与权重不同。

**代码位置：** `matching/scoring.py`。

## 54. 强制资质缺口为什么 NO_BID？

**30 秒回答：** 示例规则把 qualification 强制 GAP 视为严重准入缺口，无论其余分高低都不推荐直接投标。

**深入追问：** 这是法律判定吗？不是，教学业务规则，真实招标需要原文和专业人员判断。

**代码位置：** `../../config/scoring.yaml`。

## 55. 保存机会如何保证幂等？

**30 秒回答：** tender_id 是机会主键，服务端先查已有记录，重放同一任务返回 already_existed。签名绑定固定字段。

**深入追问：** 是否支持多服务并发唯一冲突重试？当前单工作流，本版没有完整分布式 exactly-once 机制。

**代码位置：** `../../mcp_server/bidpilot_mcp/server.py`。

## 56. RAG 怎么评测？

**30 秒回答：** 固定 requirement→expected docs，用相同 K/filter 比 vector、BM25、hybrid，分别报告 Recall、Hit Rate 和 MRR。

**深入追问：** 为什么不只看生成回答？否则无法区分检索失败和判断失败。

**代码位置：** `../../eval/retrieval_eval.py`。

## 57. Agent 怎么评测？

**30 秒回答：** 跑真实图到 HITL，统计任务完成、重检、工具/检索次数、耗时和引用存在。审批保存另有 E2E 测试。

**深入追问：** 完成率是否代表准确率？不是，匹配正确性另看有标签评测。

**代码位置：** `../../eval/agent_eval.py`。

## 58. LLM-as-Judge 有什么问题？

**30 秒回答：** 可能偏爱流畅表达，与生成模型共享偏差，并受 prompt 和样本顺序影响。应与人工标签、硬性 gates 结合。

**深入追问：** 本项目用它计算 Accuracy 吗？默认不用，以人工设计的 synthetic status 标注对比。

**代码位置：** `../../eval/match_eval.py`。

## 59. 为什么用 Recall 与 MRR？

**30 秒回答：** Recall 看有多少相关资料进候选，MRR 看正确资料是否靠前，二者对应能否找到以及是否高效利用上下文。

**深入追问：** 匹配层应该看什么？Accuracy、Macro F1 和按类别的混淆矩阵。

**代码位置：** `../../eval/retrieval_eval.py；../../eval/match_eval.py`。

## 60. Hybrid 真的更好吗？

**30 秒回答：** 当前 Lite 实测 Recall 与单路相同，MRR 高于 hash vector 但低于 BM25。只能据此说需要更难、更独立的数据和真实 embedding。

**深入追问：** 能把97.5%写成真实模型准确率吗？不能，它来自40条同域模拟规则测试。

**代码位置：** `../../artifacts/eval/latest/report.md`。

## 61. 怎么保证数据不泄漏给 FakeLLM？

**30 秒回答：** 运行 provider 不读取 eval 标签，只读输入 requirement 和检索 evidence；评测模块才读取 expected_status。规则仍与语料同域，不是独立 benchmark。

**深入追问：** 怎样加强可信度？冻结规则，另编写未见业务文档和查询。

**代码位置：** `llm/fake.py；../../eval/datasets/README.md`。

## 62. 当前项目最应优先改什么？

**30 秒回答：** 优先补独立测试集，处理复合需求跨分类检索和否定/数值范围，然后实测真实模型。生产化前再补认证、任务队列和共享 checkpoint。

**深入追问：** 为什么不先加 Kubernetes？基础能力与评测问题尚未解决，扩容不解决正确性。

**代码位置：** `rag/pipeline.py；../../docs/evaluation.md`。
