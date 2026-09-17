# MCP Server / Client 与确认写入

`mcp_server/bidpilot_mcp/server.py` 使用官方 `mcp.server.fastmcp.FastMCP`。`src/bidpilot/mcp_client/client.py` 使用 `ClientSession` 完成 initialize、list_tools/call_tool。Agent 没有 import server 业务函数。读工具使用 `data/seed/company.json`；所有记录为模拟数据。

| Tool | 输入 | 输出或行为 |
|---|---|---|
| get_company_profile | section? | 概况或单个字段 |
| get_product_capability | product, capability | 产品已登记能力；找不到返回空 |
| get_qualification | qualification_name | 精确证书匹配，found=false 不猜测 |
| get_case_study | industry, keyword? | 行业案例 |
| get_historical_bid | industry, keyword | 历史记录，不证明现有能力 |
| save_bid_opportunity | tender_id, project_name, deadline, score, recommendation, approval_token | 签名核验后写入 opportunity |

stdio：同一 Python 环境启动 `python -m bidpilot_mcp.server`，用标准输入输出传 JSON-RPC；日志只能写 stderr。一个 matcher 批次共用会话，退出时清理子进程，避免每个条款反复启动。

Streamable HTTP：`python -m bidpilot_mcp.server --transport streamable-http --port 8001`，端点 `/mcp`。客户端设置 MCP_TRANSPORT=http 与 MCP_URL。Docker 中用 mcp-server 服务名；宿主用 127.0.0.1。这里只开启受控本地演示，未配置跨网络身份认证。

写操作流程：interrupt 展示 payload → API 收到严格布尔 approve → 同一 graph thread 恢复 → Python 用共享 secret 签名固定 payload（五分钟）→ MCP 验签 → SQLAlchemy 保存。拒绝从不调用写工具。防重复依靠 tender_id 主键与已有记录检查。

秘密通过环境传入，不在报告、工具调用日志、ZIP 或 prompt 中保存。默认 Lite secret 是公开的演示值，Full 配置禁止沿用它。签名只隔离本地 Agent 读工具路径；能修改环境或直接访问数据库的用户仍具有同等权限。企业上线还需登录、权限与审计。

MCP 定义工具发现及传输协议；Function Calling 是模型输出结构化工具选择的机制；普通 REST 是业务 HTTP 接口。项目用 LangChain structured tool schema 产生 QueryPlan，再用 MCP 传输实际请求，而不是把 function calling 等同于 MCP。

测试：`test_mcp_real_stdio_reads_and_signed_idempotent_write` 覆盖六工具发现、读取、伪造 token 拒绝与幂等；`test_mcp_streamable_http` 启动真实 HTTP 服务并调用。
