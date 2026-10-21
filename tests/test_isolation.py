"""結構檢查：核心套件只依賴 stdlib 與 Pydantic，套件內部一律相對 import。"""

import ast
import json
import subprocess
import sys
from pathlib import Path

import showreceipts

PACKAGE_DIR = Path(showreceipts.__file__).parent
ALLOWED_THIRD_PARTY = {"pydantic"}
# 選配 extra 只准在 Splitter 內、且只能在函式裡 lazy import，缺套件時 split 才能附上安裝提示。
EXTRA_IMPORTS_BY_FILE = {"splitter.py": {"pypdf", "docx"}}


def _absolute_imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.append(node.module)
    return names


def _allowed(path: Path) -> set[str]:
    extras = EXTRA_IMPORTS_BY_FILE.get(str(path.relative_to(PACKAGE_DIR)), set())
    return set(sys.stdlib_module_names) | ALLOWED_THIRD_PARTY | {"__future__"} | extras


def test_isolation_core_imports_only_stdlib_and_pydantic() -> None:
    offending = {
        f"{path.relative_to(PACKAGE_DIR)}: {name}"
        for path in PACKAGE_DIR.rglob("*.py")
        for name in _absolute_imports(path)
        if name.split(".")[0] not in _allowed(path)
    }
    assert not offending, f"non-stdlib / non-pydantic imports: {sorted(offending)}"


def test_isolation_optional_extras_imported_lazily() -> None:
    offending = set()
    for rel, extras in EXTRA_IMPORTS_BY_FILE.items():
        path = PACKAGE_DIR / rel
        if not path.exists():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            offending.update(f"{rel}: {name}" for name in names if name.split(".")[0] in extras)
    assert not offending, f"import optional extras inside functions: {sorted(offending)}"


def test_isolation_core_never_imports_itself_absolutely() -> None:
    offending = {
        str(path.relative_to(PACKAGE_DIR))
        for path in PACKAGE_DIR.rglob("*.py")
        for name in _absolute_imports(path)
        if name.split(".")[0] == "showreceipts"
    }
    assert not offending, f"use relative imports inside the package: {sorted(offending)}"


def test_isolation_public_names_all_importable() -> None:
    missing = [name for name in showreceipts.__all__ if not hasattr(showreceipts, name)]
    assert not missing


# 在乾淨的直譯器裡封鎖框架、demo 與選配套件，確認核心與兩個 Adapter 仍能 import 並執行。
_BLOCKED_RUN = """
import importlib.abc, json, sys
from types import SimpleNamespace

BLOCKED = {
    "langchain", "langchain_core", "langchain_openai", "langchain_community", "langchain_text_splitters",
    "langchain_chroma", "llama_index", "chromadb", "openai", "httpx", "requests", "pydantic_settings",
    "streamlit", "fastapi", "starlette", "uvicorn", "demo", "examples", "pypdf", "docx",
}

class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in BLOCKED:
            raise ImportError(f"blocked: {name}")
        return None

sys.meta_path.insert(0, Block())
try:
    import langchain_core
except ImportError:
    pass
else:
    raise SystemExit("blocker did not block langchain_core")

import showreceipts as sr
from showreceipts.adapters import from_arrkb, from_langchain

arrkb = from_arrkb(json.load(open(sys.argv[1], encoding="utf-8")))
langchain = from_langchain([SimpleNamespace(page_content="年費 NT$4,500", metadata={"source": "card.pdf"})])
answered = sr.answer("年費多少？", arrkb, lambda system, user: "年費 NT$4,500 [2]。")
processed = sr.postprocess("年費 NT$4,500 [1]。", langchain)
loaded = {m.split(".")[0] for m in sys.modules} & BLOCKED
print(json.dumps({
    "arrkb": len(arrkb),
    "answer": [answered.answer, answered.citations[0].passage.id],
    "postprocess": [processed.answer, processed.citations[0].passage.id == langchain[0].id],
    "loaded": sorted(loaded),
}, ensure_ascii=False))
"""


def test_isolation_frameworks_blocked_core_and_adapters_still_run() -> None:
    sample = PACKAGE_DIR.parents[1] / "data" / "sample_reranked.json"

    result = subprocess.run(
        [sys.executable, "-c", _BLOCKED_RUN, str(sample)], capture_output=True, encoding="utf-8", check=False
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "arrkb": 6,
        "answer": ["年費 NT$4,500 [1]。", "465150318778054735"],
        "postprocess": ["年費 NT$4,500 [1]。", True],
        "loaded": [],
    }
