import asyncio
import json
import os
import sys
from contextlib import asynccontextmanager
from datetime import timedelta

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client

READ_TOOLS = {
    "get_company_profile",
    "get_product_capability",
    "get_qualification",
    "get_case_study",
    "get_historical_bid",
}


class EnterpriseMCPClient:
    def __init__(self, settings):
        self.settings = settings

    @asynccontextmanager
    async def connect(self):
        s = self.settings
        if s.mcp_transport == "http":
            async with streamable_http_client(s.mcp_url) as (read, write, _):
                async with ClientSession(
                    read, write, read_timeout_seconds=timedelta(seconds=s.mcp_timeout)
                ) as session:
                    await session.initialize()
                    yield session
        else:
            env = {
                **os.environ,
                "PROJECT_ROOT": str(s.project_root),
                "RUNTIME_DIR": str(s.runtime_dir),
                "DATABASE_URL": s.database_url,
                "APPROVAL_SECRET": s.approval_secret,
                "MODE": "lite",
                "PYTHONUTF8": "1",
            }
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "bidpilot_mcp.server"],
                env=env,
                cwd=str(s.project_root),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(
                    read, write, read_timeout_seconds=timedelta(seconds=s.mcp_timeout)
                ) as session:
                    await session.initialize()
                    yield session

    async def call(self, session, name, arguments, allow_write=False):
        if name not in READ_TOOLS and not (allow_write and name == "save_bid_opportunity"):
            raise ValueError("Tool not allowed in this phase")
        response = await asyncio.wait_for(session.call_tool(name, arguments), self.settings.mcp_timeout)
        if response.isError:
            raise RuntimeError("MCP tool returned an error")
        if response.structuredContent:
            return response.structuredContent
        for content in response.content:
            if content.type == "text":
                try:
                    return json.loads(content.text)
                except json.JSONDecodeError:
                    return {"text": content.text[:6000]}
        return {}
