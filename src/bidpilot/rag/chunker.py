import hashlib
from datetime import datetime, timezone
from pathlib import Path

from langchain_text_splitters import RecursiveCharacterTextSplitter

from bidpilot.agent.schemas import Evidence
from bidpilot.documents.parser import parse_document


def chunk_document(path: Path, root: Path, size=500, overlap=80, category=None):
    relative = path.relative_to(root).as_posix()
    document_id = relative
    category = category or (relative.split("/")[0] if "/" in relative else "products")
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=size, chunk_overlap=overlap, separators=["\n\n", "\n", "。", "；", " ", ""]
    )
    updated = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat()
    chunks = []
    for section in parse_document(path, max_chars=500000):
        for text in splitter.split_text(section.text):
            index = len(chunks)
            key = hashlib.sha256(f"{document_id}:{index}:{text}".encode()).hexdigest()[:16]
            chunks.append(
                Evidence(
                    evidence_id=f"EV-{key}",
                    document_id=document_id,
                    title=f"{path.stem} § {section.title}",
                    category=category,
                    source=relative,
                    chunk_index=index,
                    updated_at=updated,
                    tags=[category, path.stem],
                    chunk_text=text,
                )
            )
    return chunks
