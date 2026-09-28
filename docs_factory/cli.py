"""Command line interface for Docs Factory."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from .analyzer import analyse_repository, evidence_json
from .audit import append_audit
from .checker import check_completeness
from .constants import HONESTY_BOUNDARY, TOOL_NAME
from .diagrams import render_ascii, render_svg
from .fixtures import generate_fixtures
from .generators import generate_docs


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="df",
        description="Generate deterministic documentation from static Python AST evidence.",
        epilog=HONESTY_BOUNDARY,
    )
    parser.add_argument("--version", action="version", version=f"Docs Factory 1.0.0\n{HONESTY_BOUNDARY}")
    commands = parser.add_subparsers(dest="command", required=True)

    fixtures = commands.add_parser("fixtures", help="generate fictional synthetic fixture repositories")
    fixtures.add_argument("--out", required=True, type=Path, help="directory to contain both fixture repos")

    analyse = commands.add_parser("analyse", help="parse Python source and write JSON evidence")
    analyse.add_argument("repo", type=Path)
    analyse.add_argument("--out", type=Path, help="evidence JSON path, default: REPO/df-evidence.json")

    generate = commands.add_parser("generate", help="generate a complete docs set for a marked fixture")
    generate.add_argument("repo", type=Path)
    generate.add_argument("--out", required=True, type=Path, help="documentation output directory")
    generate.add_argument("--threshold", type=float, default=100.0, help="completeness threshold from 0 to 100")

    diagram = commands.add_parser("diagram", help="render fixture module graph as ASCII and SVG")
    diagram.add_argument("repo", type=Path)
    diagram.add_argument("--out-dir", type=Path, help="diagram directory, default: REPO/docs")

    check = commands.add_parser("check", help="compare API reference markers with current public API")
    check.add_argument("repo", type=Path)
    check.add_argument("docs", type=Path)
    check.add_argument("--threshold", type=float, default=100.0, help="minimum API coverage percentage")
    check.add_argument("--out", type=Path, help="optional completeness report JSON path")
    return parser


def _stable_hash(evidence: dict[str, Any]) -> str:
    return hashlib.sha256(evidence_json(evidence).encode("utf-8")).hexdigest()


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True))


def _write_json(path: Path, value: Any) -> None:
    path = path.expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")


def _require_fixture(evidence: dict[str, Any]) -> None:
    if not evidence["repo"].get("is_synthetic_fixture"):
        raise ValueError(
            "Documentation generation, diagrams, and completeness reports are limited to marked fictional synthetic fixtures. "
            "Use 'df fixtures' to create the supported demonstration repos."
        )


def run(args: argparse.Namespace) -> int:
    if args.command == "fixtures":
        roots = generate_fixtures(args.out)
        hashes: list[str] = []
        for root in roots:
            evidence = analyse_repository(root)
            hashes.append(_stable_hash(evidence))
        aggregate = hashlib.sha256("\n".join(hashes).encode("ascii")).hexdigest()
        append_audit(args.out, "fixtures", [path.name for path in roots], aggregate)
        _print_json(
            {
                "command": "fixtures",
                "repositories": [str(path) for path in roots],
                "evidence_hash": aggregate,
                "honesty_boundary": HONESTY_BOUNDARY,
            }
        )
        return 0

    repo = args.repo.expanduser().resolve()
    evidence = analyse_repository(repo)
    digest = _stable_hash(evidence)

    if args.command == "analyse":
        target = args.out.expanduser().resolve() if args.out else repo / "df-evidence.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(evidence_json(evidence), encoding="utf-8", newline="\n")
        append_audit(repo, "analyse", [], digest)
        _print_json(
            {
                "command": "analyse",
                "evidence_file": str(target),
                "evidence_hash": digest,
                "module_count": len(evidence["modules"]),
                "public_api_count": len(evidence["public_api"]),
                "honesty_boundary": HONESTY_BOUNDARY,
            }
        )
        return 0

    if args.command == "generate":
        _require_fixture(evidence)
        if not 0.0 <= args.threshold <= 100.0:
            raise ValueError("Threshold must be between 0 and 100.")
        out = args.out.expanduser().resolve()
        sections = generate_docs(evidence, out)
        report = check_completeness(evidence, out, args.threshold)
        report_path = out / "completeness-report.json"
        _write_json(report_path, report)
        sections.append(report_path.name)
        append_audit(repo, "generate", sections, digest, report)
        _print_json(
            {
                "command": "generate",
                "output_directory": str(out),
                "sections_generated": sections,
                "evidence_hash": digest,
                "completeness_result": report,
                "honesty_boundary": HONESTY_BOUNDARY,
            }
        )
        return 0

    if args.command == "diagram":
        _require_fixture(evidence)
        out = args.out_dir.expanduser().resolve() if args.out_dir else repo / "docs"
        out.mkdir(parents=True, exist_ok=True)
        ascii_graph = render_ascii(evidence)
        (out / "module-graph.txt").write_text(ascii_graph, encoding="utf-8", newline="\n")
        (out / "module-graph.svg").write_text(render_svg(evidence), encoding="utf-8", newline="\n")
        append_audit(repo, "diagram", ["module-graph.txt", "module-graph.svg"], digest)
        print(ascii_graph, end="")
        print(f"SVG written to {out / 'module-graph.svg'}")
        return 0

    if args.command == "check":
        _require_fixture(evidence)
        report = check_completeness(evidence, args.docs.expanduser().resolve(), args.threshold)
        if args.out:
            _write_json(args.out, report)
        append_audit(
            repo,
            "check",
            [args.out.name] if args.out else [],
            digest,
            report,
        )
        _print_json(report)
        return 0 if report["passed"] else 1

    raise ValueError(f"Unknown command: {args.command}")


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return run(args)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        audit_root = getattr(args, "out", None) if args.command == "fixtures" else getattr(args, "repo", None)
        if audit_root is not None:
            try:
                append_audit(audit_root, args.command, [], None)
            except OSError:
                pass
        print(f"{TOOL_NAME}: {error}\n{HONESTY_BOUNDARY}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
