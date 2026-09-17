import re
from pathlib import Path

from pydantic import BaseModel


class Section(BaseModel):
    text: str
    page: int | None = None
    title: str = "正文"


def split_sections(text: str, page: int | None = None) -> list[Section]:
    result, lines, title = [], [], "正文"
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            if lines:
                result.append(Section(text="\n".join(lines), page=page, title=title))
            title, lines = line.lstrip("# "), []
        elif line:
            lines.append(line)
    if lines:
        result.append(Section(text="\n".join(lines), page=page, title=title))
    return result


def parse_document(path: Path, max_chars: int = 80000) -> list[Section]:
    """Extract selectable text; never pretend that a scanned PDF has been OCR'd."""
    try:
        suffix = path.suffix.lower()
        if suffix == ".pdf":
            import fitz

            with fitz.open(path) as doc:
                if doc.is_encrypted:
                    raise ValueError("加密 PDF 暂不支持")
                sections = [s for i, p in enumerate(doc) for s in split_sections(p.get_text(), i + 1)]
        elif suffix == ".docx":
            from docx import Document
            from docx.table import Table
            from docx.text.paragraph import Paragraph

            doc = Document(path)
            lines = []
            for item in doc.iter_inner_content():
                if isinstance(item, Paragraph):
                    prefix = "## " if item.style.name.startswith("Heading") else ""
                    lines.append(prefix + item.text)
                elif isinstance(item, Table):
                    lines.extend(" | ".join(c.text for c in row.cells) for row in item.rows)
            sections = split_sections("\n".join(lines))
        elif suffix in {".md", ".txt"}:
            sections = split_sections(path.read_text(encoding="utf-8-sig"))
        else:
            raise ValueError("仅支持 PDF、DOCX、Markdown 和 UTF-8 TXT")
    except Exception as exc:
        raise ValueError(f"文档解析失败: {exc}") from exc
    size = sum(len(s.text) for s in sections)
    if size < 5:
        raise ValueError("未提取到正文；扫描 PDF 需要先 OCR")
    if size > max_chars:
        raise ValueError(f"文档超过 {max_chars} 字符，请拆分；不会静默截断")
    return sections


def normalize_text(text: str) -> str:
    return re.sub(r"[\s，。；:：、,;.!！?？\-•]+", "", text).casefold()


def normalize_requirements(requirements):
    result, seen = [], {}
    for r in requirements:
        key = normalize_text(r.text)
        if key in seen:
            old = result[seen[key]]
            old.mandatory = old.mandatory or r.mandatory
            old.weight = max(old.weight or 0, r.weight or 0) or None
            continue
        seen[key] = len(result)
        result.append(r.model_copy(update={"requirement_id": f"REQ-{len(result) + 1:03}"}))
    return result
