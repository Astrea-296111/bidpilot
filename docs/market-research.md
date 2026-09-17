# 2026 岗位与采购 Agent 调研

检索日期：2026-09-16。开发前检索了 2026 Agent JD、RFP/procurement agents、LangGraph + RAG + MCP 岗位及公开项目；随后补充核对可访问的原始招聘页。以下是定性选型依据，不是岗位频次统计，也不声称这是国内应届生招聘的代表样本。

## 岗位样本

[Citi 的 Senior LLM and Agentic AI Engineer](https://jobs.citi.com/job/chennai/senior-llm-and-agentic-ai-engineer-assistant-vice-president/287/95982093488) 原始页标注 2026-06-04。需求包含 Agent 编排、多 Agent、RAG/向量库、评估与 Python/Java 后端。该岗位要求多年经验，不能把它当成应届生门槛；本项目只借鉴可展示的工程能力。

[日经企业数字服务工程岗位](https://herp.careers/v1/nikkei/requisition-groups/78272ddb-2ae2-4cc6-be31-91c408aa7ae8) 的雇主招聘页明确涉及 LangGraph、MCP 工具、查询改写、重排、引用管理以及评测、FastAPI 和 pytest。页面未提供可核实的初始发布日期，只能称“2026-09-16 查询到的职位”，不能声称发布日期为 2026。

[Planera Agent Engineer](https://jobs.ashbyhq.com/planera/d68c8a09-a11d-409e-85ca-5d434caf3fc8) 与 [Hilbert's AI Engineer](https://jobs.ashbyhq.com/hilberts/133e25a8-f895-4c44-bfbb-d7b64db4db7b) 检索摘要涉及 Agent/MCP/结构化输出，但直接打开仅返回需要 JavaScript 的提示，因此不据此提供详细岗位统计。

## 企业场景

[BCG 2026 tech procurement 研究](https://www.bcg.com/publications/2026/scaling-agentic-ai-in-tech-procurement) 将采购 Agent 的规模化落地与组织、流程配合联系起来。对本项目的启发：保留明确业务流程、输出证据与人工确认；不能用“会调用模型”替代可执行业务闭环。

[McKinsey 2026-02-05 采购文章](https://www.mckinsey.com/capabilities/operations/our-insights/redefining-procurement-performance-in-the-era-of-agentic-ai) 讨论 agentic AI 在采购价值创造上的变化。我们据此选择 RFP requirement→企业能力→投标决策的窄场景。行业报告不构成学生项目商业收益的证据，本项目没有宣称节省多少真实成本。

## 开源观察与边界

| 原始项目 | 可借鉴方向 | 本项目的差异 |
|---|---|---|
| [TenderCortex](https://github.com/GonzaloPontnau/TenderCortex) | 多角色、文档分析、RAG | 三 Agent；要求级证据绑定与确定性 Bid 评分 |
| [BidMaster-Pro](https://github.com/guangshu100/BidMaster-Pro) | 招投标流程覆盖与合规检查 | 不生成完整标书，不做 OCR/复杂平台 |
| [MultiAgent-RFP](https://github.com/Nehan757/MultiAgent-RFP) | 三角色工作流、生成与验证 | 面向投标方评估，不做供应商邮件发送 |
| [Tender MCP](https://github.com/OjasKord/tender-mcp) | 招标业务通过 MCP 暴露工具 | 查询本地模拟企业能力并控制写操作 |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | 编排、检索与评测作为可读工程资产 | 小型业务闭环，控制上下文与工具预算 |

这些是工程学习参考，不是“优秀简历获录用”的证明。仅阅读公开介绍/官方示例后独立实现，没有整仓复制、fork 或大段源码移植。没有足够证据比较仓库最近提交活跃度，所以不编造 stars、更新速度或商业成熟度。

结论（本项目设计推断）：与其增加 Agent 数量，更值得展示可追溯证据、错误处理、人工中断、后端接口和真实评测。该结论来自上述定性样本，不是统计推断。
