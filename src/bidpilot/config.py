from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_ignore_empty=True)
    mode: Literal["lite", "full"] = "lite"
    project_root: Path = Field(default_factory=Path.cwd)
    runtime_dir: Path = Path("runtime")
    database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    qdrant_url: str = "http://localhost:6333"
    qdrant_collection: str = "bidpilot_knowledge"
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout: float = 45
    embedding_provider: Literal["auto", "hash", "local", "api"] = "auto"
    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_base_url: str = "https://api.openai.com/v1"
    embedding_api_key: str = ""
    embedding_dimensions: int = 512
    enable_reranker: bool = False
    reranker_model: str = "BAAI/bge-reranker-base"
    chunk_size: int = 500
    chunk_overlap: int = 80
    max_graph_steps: int = Field(30, ge=10, le=100)
    max_retrieval_retry: int = Field(1, ge=0, le=1)
    max_tool_calls: int = Field(10, ge=1, le=30)
    max_document_chars: int = 80000
    max_requirements: int = 100
    max_upload_mb: int = 10
    rate_limit: int = 20
    mcp_transport: Literal["stdio", "http"] = "stdio"
    mcp_url: str = "http://localhost:8001/mcp"
    mcp_timeout: float = 20
    approval_secret: str = "bidpilot-local-demo-only"

    @model_validator(mode="after")
    def paths_and_mode(self):
        self.project_root = self.project_root.resolve()
        if not self.runtime_dir.is_absolute():
            self.runtime_dir = self.project_root / self.runtime_dir
        if not self.database_url:
            self.database_url = (
                "sqlite+aiosqlite:///" + (self.runtime_dir / "bidpilot.db").as_posix()
                if self.mode == "lite"
                else "postgresql+asyncpg://bidpilot:bidpilot@localhost:5432/bidpilot"
            )
        if self.embedding_provider == "auto":
            self.embedding_provider = "hash" if self.mode == "lite" else "local"
        if self.mode == "full" and (not self.llm_api_key or not self.llm_model):
            raise ValueError("Full mode requires LLM_API_KEY and LLM_MODEL")
        if self.mode == "full" and self.approval_secret == "bidpilot-local-demo-only":
            raise ValueError("Set APPROVAL_SECRET to the same random value for backend and MCP")
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP must be smaller than CHUNK_SIZE")
        return self

    @property
    def knowledge_dir(self):
        return self.project_root / "data" / "company_knowledge"

    def prepare(self):
        for name in ("uploads", "knowledge", "embeddings"):
            (self.runtime_dir / name).mkdir(parents=True, exist_ok=True)
