"""Import rules of the ``typeoke_core`` package, enforced with the ``ast`` module.

The package is pure computation: no cloud SDK, no logging toolkit, no HTTP client
and no network or file input/output. The deny list below is explicit; a module that
needs something on it must be reported, not silently allowed.
"""

import ast
from pathlib import Path

import pytest

PACKAGE_NAME = "typeoke_core"
PACKAGE_DIR = Path(__file__).resolve().parent.parent / PACKAGE_NAME

ALLOWED_FILES = frozenset({"__init__.py", "config.py", "models.py", "scoring.py", "timeline.py"})
FORBIDDEN_ENTRIES = frozenset({"domain", "application", "adapters"})

# Cloud SDKs and logging toolkits.
DENIED_SDKS = ("boto3", "botocore", "aws_lambda_powertools")
# HTTP and network clients.
DENIED_NETWORK = (
    "urllib.request",
    "urllib3",
    "http.client",
    "requests",
    "httpx",
    "aiohttp",
    "socket",
    "ssl",
)
# File, process and database input/output.
DENIED_IO = ("os", "pathlib", "io", "shutil", "tempfile", "subprocess", "sqlite3")
DENIED_MODULES = DENIED_SDKS + DENIED_NETWORK + DENIED_IO
# Builtins that perform input/output when called.
DENIED_CALLS = ("open",)
# Calls that import a module from a string.
DYNAMIC_IMPORTERS = ("__import__", "import_module")


def _is_denied(name: str) -> bool:
    return any(name == denied or name.startswith(denied + ".") for denied in DENIED_MODULES)


def _resolve_from(node: ast.ImportFrom, module_path: tuple[str, ...]) -> str:
    """Return the absolute dotted name of the module named by a ``from`` import."""
    if node.level == 0:
        return node.module or ""
    base = module_path[: len(module_path) - node.level]
    parts = list(base) + ([node.module] if node.module else [])
    return ".".join(parts)


def _imported_names(node: ast.Import | ast.ImportFrom, module_path: tuple[str, ...]) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    source = _resolve_from(node, module_path)
    names = [source]
    names.extend(f"{source}.{alias.name}" for alias in node.names if alias.name != "*")
    return names


def _call_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _literal_import_target(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Constant):
        value = node.args[0].value
        if isinstance(value, str):
            return value
    return None


def _module_path(package_dir: Path, file: Path) -> tuple[str, ...]:
    """Package path of the module, as seen by relative imports."""
    return (package_dir.name, *file.relative_to(package_dir).with_suffix("").parts)


def find_import_violations(package_dir: Path) -> list[str]:
    """Return one message per offending import or call in the package."""
    violations: list[str] = []
    for file in sorted(package_dir.rglob("*.py")):
        module_path = _module_path(package_dir, file)
        label = file.relative_to(package_dir.parent).as_posix()
        tree = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import | ast.ImportFrom):
                for name in _imported_names(node, module_path):
                    if _is_denied(name):
                        violations.append(f"{label}:{node.lineno}: forbidden import '{name}'")
            elif isinstance(node, ast.Call):
                called = _call_name(node)
                if called in DENIED_CALLS and isinstance(node.func, ast.Name):
                    violations.append(f"{label}:{node.lineno}: forbidden call '{called}()'")
                elif called in DYNAMIC_IMPORTERS:
                    target = _literal_import_target(node)
                    if target is not None and _is_denied(target):
                        violations.append(
                            f"{label}:{node.lineno}: forbidden dynamic import '{target}'"
                        )
    return violations


def find_layout_violations(package_dir: Path) -> list[str]:
    """Return one message per unexpected entry in the package folder."""
    violations: list[str] = []
    for entry in sorted(package_dir.iterdir()):
        if entry.name == "__pycache__":
            continue
        if entry.name in FORBIDDEN_ENTRIES:
            violations.append(f"forbidden folder '{entry.name}'")
        elif entry.name not in ALLOWED_FILES:
            violations.append(f"unexpected entry '{entry.name}'")
    present = {entry.name for entry in package_dir.iterdir()}
    violations.extend(f"missing module '{name}'" for name in sorted(ALLOWED_FILES - present))
    return violations


def _write_package(root: Path, module_source: str) -> Path:
    package = root / PACKAGE_NAME
    package.mkdir()
    for name in ALLOWED_FILES:
        (package / name).write_text("", encoding="utf-8")
    (package / "scoring.py").write_text(module_source, encoding="utf-8")
    return package


def test_package_has_no_forbidden_imports() -> None:
    assert find_import_violations(PACKAGE_DIR) == []


def test_package_layout_is_flat() -> None:
    assert find_layout_violations(PACKAGE_DIR) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import boto3\n", "scoring.py:1: forbidden import 'boto3'"),
        ("import os.path\n", "scoring.py:1: forbidden import 'os.path'"),
        ("from botocore.config import Config\n", "forbidden import 'botocore.config'"),
        ("from urllib import request\n", "forbidden import 'urllib.request'"),
        ("x = 1\nwith open('f') as handle:\n    pass\n", "scoring.py:2: forbidden call 'open()'"),
        ("import importlib\nimportlib.import_module('requests')\n", "dynamic import 'requests'"),
        ("__import__('aws_lambda_powertools')\n", "dynamic import 'aws_lambda_powertools'"),
    ],
)
def test_detects_forbidden_usage(tmp_path: Path, source: str, expected: str) -> None:
    package = _write_package(tmp_path, source)
    messages = find_import_violations(package)
    assert any(expected in message for message in messages), messages


def test_allows_pure_imports(tmp_path: Path) -> None:
    source = "import json\nimport math\nfrom . import config\nfrom .models import Line\n"
    package = _write_package(tmp_path, source)
    assert find_import_violations(package) == []


def test_resolves_relative_imports_to_absolute_names(tmp_path: Path) -> None:
    package = tmp_path / "socket"
    package.mkdir()
    (package / "inner.py").write_text("from . import x\nfrom .y import z\n", encoding="utf-8")
    messages = find_import_violations(package)
    assert [m.split(": ", 1)[1] for m in messages] == [
        "forbidden import 'socket'",
        "forbidden import 'socket.x'",
        "forbidden import 'socket.y'",
        "forbidden import 'socket.y.z'",
    ]


def test_detects_layout_violations(tmp_path: Path) -> None:
    package = _write_package(tmp_path, "")
    (package / "adapters").mkdir()
    (package / "extra.py").write_text("", encoding="utf-8")
    (package / "__pycache__").mkdir()
    (package / "timeline.py").unlink()
    assert find_layout_violations(package) == [
        "forbidden folder 'adapters'",
        "unexpected entry 'extra.py'",
        "missing module 'timeline.py'",
    ]
