from pathlib import Path

import pytest

from bidpilot.config import Settings

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def settings(tmp_path):
    return Settings(
        _env_file=None,
        mode="lite",
        project_root=ROOT,
        runtime_dir=tmp_path,
        database_url="",
        embedding_provider="hash",
        rate_limit=1000,
        enable_reranker=False,
    )
