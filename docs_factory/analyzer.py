"""Deterministic static analysis of Python repositories using the AST module."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path
from typing import Any

from .constants import DETERMINISTIC_SEED, HONESTY_BOUNDARY, TOOL_NAME
from .fixtures import verify_fixture

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "__pycache__",
    "site-packages",
    "build",
    "dist",
}


def _module_name(path: Path, root: Path) -> str:
    relative = path.relative_to(root).with_suffix("")
    parts = list(relative.parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) if parts else root.name.replace("-", "_")


def _source_files(root: Path) -> list[Path]:
    found: list[Path] = []
    for directory, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if name not in SKIP_DIRS and not name.startswith("."))
        base = Path(directory)
        found.extend(base / filename for filename in filenames if filename.endswith(".py"))
    return sorted(found, key=lambda item: item.relative_to(root).as_posix())


def _unparse(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)
    except (AttributeError, ValueError):
        return "?"


def _argument_signature(args: ast.arguments) -> str:
    pieces: list[str] = []
    positional = list(args.posonlyargs) + list(args.args)
    defaults = [None] * (len(positional) - len(args.defaults)) + list(args.defaults)
    posonly_count = len(args.posonlyargs)
    for index, (arg, default) in enumerate(zip(positional, defaults)):
        text = arg.arg
        if arg.annotation:
            text += ": " + _unparse(arg.annotation)
        if default is not None:
            text += " = " + _unparse(default)
        pieces.append(text)
        if posonly_count and index + 1 == posonly_count:
            pieces.append("/")

    if args.vararg:
        text = "*" + args.vararg.arg
        if args.vararg.annotation:
            text += ": " + _unparse(args.vararg.annotation)
        pieces.append(text)
    elif args.kwonlyargs:
        pieces.append("*")

    for arg, default in zip(args.kwonlyargs, args.kw_defaults):
        text = arg.arg
        if arg.annotation:
            text += ": " + _unparse(arg.annotation)
        if default is not None:
            text += " = " + _unparse(default)
        pieces.append(text)

    if args.kwarg:
        text = "**" + args.kwarg.arg
        if args.kwarg.annotation:
            text += ": " + _unparse(args.kwarg.annotation)
        pieces.append(text)
    return ", ".join(pieces)


def _function_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    text = f"{node.name}({_argument_signature(node.args)})"
    if node.returns:
        text += " -> " + _unparse(node.returns)
    return text


def _decorator_name(node: ast.expr) -> str:
    target = node.func if isinstance(node, ast.Call) else node
    return _unparse(target)


def _class_signature(node: ast.ClassDef) -> str:
    initializer = next(
        (
            item
            for item in node.body
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item.name == "__init__"
        ),
        None,
    )
    if initializer is None:
        return f"{node.name}()"
    args = initializer.args
    posonlyargs = list(args.posonlyargs)
    ordinary_args = list(args.args)
    if posonlyargs and posonlyargs[0].arg in {"self", "cls"}:
        posonlyargs = posonlyargs[1:]
    elif ordinary_args and ordinary_args[0].arg in {"self", "cls"}:
        ordinary_args = ordinary_args[1:]
    if posonlyargs != list(args.posonlyargs) or ordinary_args != list(args.args):
        args = ast.arguments(
            posonlyargs=posonlyargs,
            args=ordinary_args,
            vararg=args.vararg,
            kwonlyargs=args.kwonlyargs,
            kw_defaults=args.kw_defaults,
            kwarg=args.kwarg,
            defaults=args.defaults,
        )
    return f"{node.name}({_argument_signature(args)})"


def _internal_imports(
    tree: ast.AST, module_name: str, is_package: bool, known_modules: set[str]
) -> list[str]:
    targets: set[str] = set()
    package = module_name if is_package else module_name.rpartition(".")[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            candidates = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base_parts = package.split(".") if package else []
                remove = max(0, node.level - 1)
                if remove:
                    base_parts = base_parts[: max(0, len(base_parts) - remove)]
                base = ".".join(base_parts)
                imported = node.module or ""
                full = ".".join(part for part in (base, imported) if part)
            else:
                full = node.module or ""
            candidates = [full] if full else []
            for alias in node.names:
                if alias.name != "*" and full:
                    candidates.append(f"{full}.{alias.name}")
        else:
            continue

        for candidate in candidates:
            match = candidate
            while match and match not in known_modules:
                match = match.rpartition(".")[0]
            if match and match != module_name:
                targets.add(match)
    return sorted(targets)


def _is_main_guard(node: ast.If) -> bool:
    test = node.test
    if not isinstance(test, ast.Compare) or len(test.ops) != 1 or len(test.comparators) != 1:
        return False
    left, right = test.left, test.comparators[0]
    return (
        isinstance(test.ops[0], (ast.Eq, ast.Is))
        and (
            isinstance(left, ast.Name)
            and left.id == "__name__"
            and isinstance(right, ast.Constant)
            and right.value == "__main__"
            or isinstance(right, ast.Name)
            and right.id == "__name__"
            and isinstance(left, ast.Constant)
            and left.value == "__main__"
        )
    )


def _fixture_metadata(root: Path) -> dict[str, Any]:
    marker = root / ".docs-factory-fixture.json"
    if not marker.is_file():
        return {"is_synthetic_fixture": False, "fixture_name": None, "rough_edges": []}
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"is_synthetic_fixture": False, "fixture_name": None, "rough_edges": []}
    name = str(data.get("name", ""))
    if (
        data.get("synthetic") is not True
        or data.get("generated_by") != TOOL_NAME
        or not verify_fixture(root, name)
    ):
        return {"is_synthetic_fixture": False, "fixture_name": None, "rough_edges": []}
    return {
        "is_synthetic_fixture": True,
        "fixture_name": name,
        "rough_edges": sorted(str(value) for value in data.get("rough_edges", [])),
    }


def analyse_repository(repo: str | Path) -> dict[str, Any]:
    """Parse Python modules and return a stable, JSON-serializable evidence object."""
    root = Path(repo).expanduser().resolve()
    if not root.is_dir():
        raise ValueError(f"Repository directory does not exist: {root}")

    paths = _source_files(root)
    path_to_name = {path: _module_name(path, root) for path in paths}
    known_modules = set(path_to_name.values())
    trees: dict[str, ast.AST] = {}
    modules: list[dict[str, Any]] = []
    api: list[dict[str, Any]] = []
    entry_points: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for path in paths:
        name = path_to_name[path]
        rel_path = path.relative_to(root).as_posix()
        source = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(source, filename=rel_path)
        except SyntaxError as error:
            parse_errors.append(
                {"path": rel_path, "line": error.lineno or 0, "message": error.msg}
            )
            modules.append(
                {
                    "name": name,
                    "path": rel_path,
                    "docstring": "",
                    "docstring_present": False,
                    "coverage": {"documented": 0, "total": 0, "percent": 100.0},
                    "imports": [],
                }
            )
            continue

        trees[name] = tree
        docstring = ast.get_docstring(tree) or ""
        public_nodes = [
            node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and not node.name.startswith("_")
        ]
        documented = sum(bool(ast.get_docstring(node)) for node in public_nodes)
        total = len(public_nodes)
        coverage = round(100.0 * documented / total, 1) if total else 100.0
        is_package = path.name == "__init__.py"
        imports = _internal_imports(tree, name, is_package, known_modules)
        modules.append(
            {
                "name": name,
                "path": rel_path,
                "docstring": docstring,
                "docstring_present": bool(docstring),
                "coverage": {"documented": documented, "total": total, "percent": coverage},
                "imports": imports,
            }
        )

        for node in public_nodes:
            kind = "class" if isinstance(node, ast.ClassDef) else "function"
            signature = _class_signature(node) if kind == "class" else _function_signature(node)
            item = {
                "id": f"{name}.{node.name}",
                "module": name,
                "name": node.name,
                "kind": kind,
                "signature": signature,
                "decorators": [_decorator_name(item) for item in node.decorator_list],
                "docstring": ast.get_docstring(node) or "",
                "docstring_present": bool(ast.get_docstring(node)),
                "path": rel_path,
                "line": node.lineno,
            }
            api.append(item)

        for node in ast.walk(tree):
            if isinstance(node, ast.If) and _is_main_guard(node):
                entry_points.append(
                    {
                        "module": name,
                        "kind": "main_guard",
                        "name": Path(rel_path).stem,
                        "path": rel_path,
                        "line": node.lineno,
                    }
                )
        for node in tree.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                continue
            if node.name == "main" and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                entry_points.append(
                    {
                        "module": name,
                        "kind": "main_function",
                        "name": node.name,
                        "path": rel_path,
                        "line": node.lineno,
                    }
                )
            if any(_decorator_name(item).split(".")[-1] == "cli_entrypoint" for item in node.decorator_list):
                entry_points.append(
                    {
                        "module": name,
                        "kind": "marked_cli",
                        "name": node.name,
                        "path": rel_path,
                        "line": node.lineno,
                    }
                )
        if any(line.strip() == "# docs-factory: cli" for line in source.splitlines()[:5]):
            entry_points.append(
                {
                    "module": name,
                    "kind": "marked_cli_script",
                    "name": Path(rel_path).stem,
                    "path": rel_path,
                    "line": 1,
                }
            )

    modules.sort(key=lambda item: item["name"])
    api.sort(key=lambda item: item["id"])
    entry_points.sort(key=lambda item: (item["module"], item["kind"], item["name"], item["line"]))
    import_edges = [
        {"from": module["name"], "to": target}
        for module in modules
        for target in module["imports"]
    ]
    import_edges.sort(key=lambda item: (item["from"], item["to"]))
    api_doc_count = sum(item["docstring_present"] for item in api)
    api_total = len(api)
    per_module = [
        {
            "module": item["name"],
            "documented": item["coverage"]["documented"],
            "total": item["coverage"]["total"],
            "percent": item["coverage"]["percent"],
        }
        for item in modules
    ]
    fixture_data = _fixture_metadata(root)
    return {
        "schema_version": 1,
        "tool": TOOL_NAME,
        "repo": {
            "path": str(root),
            "name": root.name,
            **fixture_data,
        },
        "honesty_boundary": HONESTY_BOUNDARY,
        "determinism": {
            "seed": DETERMINISTIC_SEED,
            "ordering": "lexicographic",
        },
        "modules": modules,
        "import_edges": import_edges,
        "entry_points": entry_points,
        "public_api": api,
        "docstring_coverage": {
            "documented": api_doc_count,
            "total": api_total,
            "percent": round(100.0 * api_doc_count / api_total, 1) if api_total else 100.0,
            "per_module": per_module,
        },
        "parse_errors": parse_errors,
    }


def evidence_json(evidence: dict[str, Any]) -> str:
    """Serialize evidence with stable key order and a final newline."""
    return json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
