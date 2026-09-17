import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from bidpilot.agent.schemas import QueryPlan
from bidpilot.llm.openai_compatible import OpenAICompatibleProvider
from bidpilot.mcp_client.client import EnterpriseMCPClient


async def test_mcp_streamable_http(settings):
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "MODE": "lite",
        "PROJECT_ROOT": str(settings.project_root),
        "RUNTIME_DIR": str(settings.runtime_dir),
        "PYTHONUTF8": "1",
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "bidpilot_mcp.server",
            "--transport",
            "streamable-http",
            "--port",
            str(port),
        ],
        cwd=settings.project_root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        async with httpx.AsyncClient(timeout=1) as http:
            for _ in range(50):
                try:
                    await http.get(f"http://127.0.0.1:{port}/mcp")
                    break
                except httpx.HTTPError:
                    await asyncio.sleep(0.1)
            else:
                raise AssertionError("MCP HTTP server did not start")
        settings.mcp_transport = "http"
        settings.mcp_url = f"http://127.0.0.1:{port}/mcp"
        client = EnterpriseMCPClient(settings)
        async with client.connect() as session:
            result = await client.call(session, "get_qualification", {"qualification_name": "ISO27001"})
            assert result["found"] and result["record"]["id"] == "DEMO-ISO27001-001"
    finally:
        process.terminate()
        await asyncio.to_thread(process.wait, 10)


async def test_openai_compatible_structured_schema_and_retry(settings):
    """Actual LangChain/OpenAI HTTP exchange against a free local protocol stub."""
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(body)
            # First response violates the Pydantic max=2 constraint; second is valid.
            arguments = {
                "queries": ["a", "b", "c"] if len(calls) == 1 else ["Kubernetes"],
                "tool": "none",
            }
            name = body["tools"][0]["function"]["name"]
            response = {
                "id": "stub",
                "object": "chat.completion",
                "created": 1,
                "model": "stub-model",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "tool_calls",
                        "message": {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": "call1",
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                            ],
                        },
                    }
                ],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
            }
            data = json.dumps(response).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        settings.llm_api_key = "test-no-paid-service"
        settings.llm_model = "stub-model"
        settings.llm_base_url = f"http://127.0.0.1:{server.server_port}/v1"
        provider = OpenAICompatibleProvider(settings)
        result = await provider.structured(
            "query_rewrite", QueryPlan, {"requirement": {"text": "Kubernetes"}}
        )
        assert result.queries == ["Kubernetes"] and len(calls) == 2
        assert calls[0]["model"] == "stub-model"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
