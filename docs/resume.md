# 简历与60秒介绍

**BidPilot —— 基于 LangGraph + Agentic RAG + MCP 的招投标智能分析 Agent**

技术栈：Python / FastAPI / LangGraph / LangChain / Qdrant / MCP / SQLAlchemy / PostgreSQL / Redis / Docker

- 基于 LangGraph 构建需求抽取、能力匹配与独立复核三个 Agent，通过 Supervisor、条件路由与一次检索重试形成 RFP→需求矩阵→投标建议闭环；使用 checkpoint 和 interrupt/resume 支持人工确认后保存机会。
- 实现 Qdrant + BM25 双路召回、RRF 融合、metadata filter、查询改写和可选 CrossEncoder 接口，为 MATCH/PARTIAL/GAP 绑定真实检索证据；采用 Python/YAML 确定性评分及强制资质缺口否决规则。
- 使用官方 MCP SDK 实现六个企业工具及 stdio/HTTP 客户端，结合 FastAPI、SSE 和 SQLAlchemy 提供可运行 Lite 演示；建立16份 RFP、40条检索与40条匹配的合成评测，记录对照结果与跨分类复合需求坏例，并提供 PostgreSQL/Redis 的 Full 配置。

若要写数值，必须标明“离线合成 fixture + FakeLLM”，例如：40条模拟匹配 Accuracy 97.5%、Macro F1 0.9687；不可写成真实业务泛化准确率或真实 LLM 效果。可选 reranker、Full 基础设施、真实 Windows 尚未实测，不能写“已生产落地/已性能优化”。

## 60秒介绍

我做了一个招投标分析 Agent，解决拿到 RFP 后逐条核对企业能力的问题。系统先从 PDF/DOCX 提取带来源的需求，Matcher 用企业知识库的向量和 BM25 双路检索，经 RRF 得到证据，并通过 MCP 查询结构化企业记录。Reviewer 检查证据和结论，最多允许一次重新检索。最后由 Python 按明确规则计算 Bid/No-Bid，输出应答大纲，并在写入机会前用 LangGraph 暂停等待人确认。后端有 FastAPI、SSE 和数据库；我还做了 vector、BM25、hybrid 的对照评测。当前是模拟数据的可运行教学工程，评测发现技术与服务复合需求会受分类过滤影响，这也是下一步改进重点。
