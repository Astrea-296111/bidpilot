# 参考资料与原创边界

访问日期：2026-09-16。以下是流程或 API 学习来源，没有复制仓库源码。

| 来源 | 用途 |
|---|---|
| [LangGraph 官方 Interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | checkpointer、thread_id、interrupt 与 Command(resume)；本项目见 agent/nodes.py |
| [LangGraph 官方仓库](https://github.com/langchain-ai/langgraph) | StateGraph 与条件路由概念 |
| [MCP 官方 Python SDK](https://github.com/modelcontextprotocol/python-sdk) | FastMCP、ClientSession、stdio 与 Streamable HTTP |
| [Qdrant 官方文档](https://qdrant.tech/documentation/) | Local/Server 向量检索与 payload filter |
| [LangChain Open Deep Research](https://github.com/langchain-ai/open_deep_research) | 可读 Agent 工作流与评估组织 |
| [TenderCortex](https://github.com/GonzaloPontnau/TenderCortex) | RFP 多角色业务分工 |
| [BidMaster-Pro](https://github.com/guangshu100/BidMaster-Pro) | 招投标业务范围参考 |
| [MultiAgent-RFP](https://github.com/Nehan757/MultiAgent-RFP) | 采购流程与验证职责分离 |
| [Tender MCP](https://github.com/OjasKord/tender-mcp) | 采购业务工具接口参考 |

招聘与行业原文、可访问性限制见 [market-research.md](market-research.md)。软件接口以实际安装版本与集成测试为准，不依据博客猜测 API。依赖本身保留各自许可证；AuroraSoft 模拟数据和本项目代码为本次独立编写。
