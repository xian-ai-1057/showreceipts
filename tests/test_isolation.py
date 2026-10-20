"""結構檢查：核心套件只依賴 stdlib 與 Pydantic，套件內部一律相對 import。"""

import ast
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
