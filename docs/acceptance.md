# 交付验收记录

日期：2026-09-16。环境：Linux / Python 3.12.14。以下区分“实测”与“代码支持”，不以 CI 配置冒充远端运行。

## 已执行

- [x] 31 项 pytest：unit / integration / E2E，全部通过。
- [x] Ruff 检查通过；Python compileall 通过。
- [x] PDF、DOCX 上传后完成解析、需求抽取、分类、检索、匹配、复核、评分、引用大纲。
- [x] 真实 LangGraph StateGraph / Supervisor / Conditional Edge / checkpoint / 一次重检。
- [x] 重启 service 后从人工确认 checkpoint 恢复；Reject 不创建机会；重复审批被拒绝。
- [x] 真实官方 MCP stdio 子进程，六工具发现、查询、签名确认写入与幂等。
- [x] 真实 Streamable HTTP MCP server/client 查询。
- [x] OpenAI-compatible provider 对本地 HTTP 协议 stub 的 schema 校验和重试。没有调用付费 LLM。
- [x] SQLite 业务事务与持久报告；Qdrant Local 真实查询和 metadata filter。
- [x] Hash embedding、BM25、RRF 与 Hybrid、短期上下文、MemoryCache、限流。
- [x] API 端到端测试，以及真实 Uvicorn HTTP 启动、PDF 上传、异步分析、SSE node/retrieval/result。
- [x] Streamlit AppTest 运行页面、渲染两张 dataframe、点击 Approve 后由 MCP 保存成功，无 UI 异常。
- [x] 16 RFP 抽取评测、40 检索对照、40 匹配、16 Agent 流程，逐条结果与数据哈希已保存。
- [x] 25 份企业知识 Markdown、16 RFP Markdown、额外 PDF/DOCX 与生成脚本。
- [x] Windows PowerShell 脚本、Docker Compose、GitHub Actions、学习指南和62题面试文档。
- [x] ZIP 完整性与排除规则检查；干净解压到含中文和空格的目录后，CLI 分析、显式 Approve 与 MCP 保存通过（Linux）。

## 未在本环境验证

- [ ] Windows 10/11 的实际 PowerShell 执行：当前没有 Windows/pwsh。已检查 pathlib/sys.executable、脚本根目录与参数处理，并提供 Windows CI。
- [ ] Docker Compose Full 全栈：当前没有 Docker Desktop/daemon。
- [ ] PostgreSQL / Redis / Qdrant Server 实例的联合运行与故障演练：实现与配置已提供。
- [ ] 真实供应商 LLM 的业务效果、BGE 小模型的语义召回、CrossEncoder rerank：NOT_MEASURED。
- [ ] 浏览器截图级视觉验收：UI 已通过 Streamlit AppTest 的结构/操作冒烟，未做截图比较。
- [ ] GitHub Actions 远端执行：工作流已提供，未上传/触发。

## 测量解释

Lite 抽取 F1=1.0；检索 Recall@4 都为1.0，MRR 分别为 Vector 0.83125、BM25 0.925、Hybrid 0.88333；匹配 Accuracy 0.975 / Macro F1 0.96871；16/16 图任务到达 HITL；引用存在率1.0。仅针对模拟 fixture + FakeLLM/hash，不代表真实企业、真实模型或泛化效果。

已知 bad case：M034 复合技术/服务条件被 technical filter 限制，真实标注 MATCH、实际 PARTIAL。正文报告保留这个缺口。平均耗时与调用次数以本次 summary.json 为准，受缓存与机器影响。

证据文件：`artifacts/package-verification.json`、`artifacts/test-results.txt`、`artifacts/http-ui-smoke.json`、`artifacts/http-smoke.log`、`artifacts/eval/latest/summary.json`、`artifacts/eval/latest/report.md`。

## 交付边界

本项目可运行、可学习、可复现，面向单机求职演示。未实现认证、租户隔离、分布式任务执行、OCR 或完整标书生成。Full 模式需要配置真实 Key/模型并在用户环境验证；MCP 写失败不会被当作成功。
