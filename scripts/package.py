"""Create a source-only ZIP; never include secrets, environments, databases or model caches."""

from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

EXCLUDED_DIRS = {
    ".venv",
    ".git",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    "runtime",
    "build",
    "dist",
    "node_modules",
    ".cache",
}


def package(root=None, output=None):
    root = root or Path(__file__).resolve().parents[1]
    output = output or root.parent / "bidpilot.zip"
    count = 0
    with ZipFile(output, "w", ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(root.rglob("*")):
            rel = path.relative_to(root)
            if not path.is_file() or any(
                p in EXCLUDED_DIRS or p.endswith(".egg-info") for p in rel.parts
            ):
                continue
            if path.name == ".env" or path.suffix in {".pyc", ".db", ".sqlite", ".sqlite3", ".zip"}:
                continue
            archive.write(path, Path("bidpilot") / rel)
            count += 1
    print(f"Created {output} ({count} files, {output.stat().st_size:,} bytes)")
    return output


if __name__ == "__main__":
    package()
