"""Deterministic section templates fed only by static analysis evidence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from .analyzer import evidence_json
from .constants import HONESTY_BOUNDARY, honesty_markdown
from .diagrams import render_ascii, render_svg

SECTION_FILES = {
    "readme": "README.md",
    "architecture": "architecture.md",
    "concepts": "concepts.md",
    "install": "install.md",
    "tutorials": "tutorials.md",
    "api_reference": "api-reference.md",
    "troubleshooting": "troubleshooting.md",
    "onboarding": "onboarding.md",
}


def _page(title: str, body: list[str]) -> str:
    return f"# {title}\n\n{honesty_markdown()}\n\n" + "\n".join(body).rstrip() + "\n"


def _package_name(evidence: dict[str, Any]) -> str:
    for module in evidence["modules"]:
        if "." in module["name"]:
            return module["name"].split(".", 1)[0]
    return evidence["repo"].get("fixture_name") or evidence["repo"]["name"].replace("-", "_")


def _entry_label(entry: dict[str, Any], package: str) -> str:
    if entry["kind"] == "main_guard":
        return f"`python -m {package}` via `{entry['path']}`"
    if entry["kind"] == "main_function":
        return f"`{entry['module']}.{entry['name']}()` in `{entry['path']}`"
    return f"`{entry['module']}.{entry['name']}` ({entry['kind']}) in `{entry['path']}`"


def _readme(evidence: dict[str, Any]) -> str:
    name = evidence["repo"].get("fixture_name") or evidence["repo"]["name"]
    modules = evidence["modules"]
    entries = evidence["entry_points"]
    package = _package_name(evidence)
    body = [
        f"## Purpose\n\n`{name}` is a fictional synthetic fixture. This page is generated from Python AST evidence.",
        "## Install\n\nUse Python 3.10 or newer. No install step or third-party runtime package is needed for this synthetic fixture. Run the detected entry point from the repository root.",
        "## Quickstart\n\nDetected entry points:",
    ]
    body.extend(f"- {_entry_label(entry, package)}" for entry in entries)
    if not entries:
        body.append("- No entry points were detected from the parsed source.")
    body.extend(["## Architecture\n\n```text", *[f"{module['name']} [{module['coverage']['percent']:.1f}% docstring coverage]" for module in modules]])
    edges = evidence["import_edges"]
    body.extend(f"{edge['from']} -> {edge['to']}" for edge in edges)
    if not edges:
        body.append("(no internal import edges)")
    body.extend(["```", f"\nThe module map includes {len(modules)} parsed modules and {len(edges)} internal import edges."])
    return _page(f"{name.replace('_', ' ').title()} Documentation", body)


def _architecture(evidence: dict[str, Any]) -> str:
    body = ["## Module layers", ""]
    for module in evidence["modules"]:
        summary = module["docstring"].splitlines()[0] if module["docstring"] else "No module docstring was found."
        body.append(f"- `{module['name']}`: {summary} ({module['coverage']['percent']:.1f}% public API docstring coverage)")
    body.extend(["", "## Dependencies", ""])
    if evidence["import_edges"]:
        body.extend(f"- `{edge['from']}` imports `{edge['to']}`" for edge in evidence["import_edges"])
    else:
        body.append("No internal module imports were detected.")
    body.extend(["", "## Text graph", "", "```text"])
    body.extend(f"{edge['from']} -> {edge['to']}" for edge in evidence["import_edges"])
    body.extend(["```", "", "The graph and coverage labels are sorted and rendered from the analyzer evidence."])
    return _page("Architecture", body)


def _concepts(evidence: dict[str, Any]) -> str:
    body = ["## Concepts from module docstrings", ""]
    for module in evidence["modules"]:
        description = module["docstring"] or "No module docstring was found in static evidence."
        body.append(f"### `{module['name']}`\n\n{description}\n")
    body.append("Module names and summaries come directly from parsed source docstrings.")
    return _page("Concepts", body)


def _install(evidence: dict[str, Any]) -> str:
    package = _package_name(evidence)
    body = [
        "## Requirements\n\nPython 3.10 or newer. The fictional fixture uses no third-party runtime packages.",
        "## Run from the fixture root\n\nNo package installation is required. Start Python in the fixture repository root so its source package is on the import path.",
        f"## Verify the entry point\n\nThe analyzed import package is `{package}`. Detected entry points are listed below:",
    ]
    body.extend(f"- {_entry_label(entry, package)}" for entry in evidence["entry_points"])
    if not evidence["entry_points"]:
        body.append("- No executable entry point was detected.")
    body.extend(["", "The source evidence does not include dependency installation instructions beyond the Python package layout."])
    return _page("Install Guide", body)


def _tutorials(evidence: dict[str, Any]) -> str:
    body = ["## Run a detected entry point", ""]
    if evidence["entry_points"]:
        for entry in evidence["entry_points"]:
            body.extend([f"### `{entry['module']}`: {entry['kind']}", "", f"Detected in `{entry['path']}` at line {entry['line']}.", "", f"Entry point: {_entry_label(entry, _package_name(evidence))}.", ""])
    else:
        body.append("No entry points were detected, so the analyzer has no executable tutorial target.")
    examples = [item for item in evidence["public_api"] if item["kind"] == "function" and item["docstring_present"]]
    if examples:
        item = examples[0]
        body.extend(["## Example public function", "", f"`{item['signature']}` is described by this source docstring:", "", f"> {item['docstring'].splitlines()[0]}"])
    return _page("Tutorials", body)


def _api_reference(evidence: dict[str, Any]) -> str:
    body = ["## Extracted public API", "", "Signatures and descriptions below come from top-level Python definitions and their docstrings.", ""]
    documented = [item for item in evidence["public_api"] if item["docstring_present"]]
    for item in documented:
        body.extend(
            [
                f"<!-- df-api: {item['id']} -->",
                f"### `{item['signature']}`",
                "",
                f"Kind: {item['kind']}. Source: `{item['path']}:{item['line']}`.",
                "",
                item["docstring"],
                "",
            ]
        )
    missing = [item["id"] for item in evidence["public_api"] if not item["docstring_present"]]
    body.extend(["## Public API without source docstrings", ""])
    if missing:
        body.extend(f"- `{item_id}` is not included as a documented API entry because its source definition has no docstring." for item_id in missing)
    else:
        body.append("Every extracted public API item has a source docstring.")
    return _page("API Reference", body)


def _troubleshooting(evidence: dict[str, Any]) -> str:
    body = ["## Observed rough edges", ""]
    rough_edges = evidence["repo"].get("rough_edges", [])
    if rough_edges:
        body.extend(f"- {item}" for item in rough_edges)
    else:
        body.append("No fixture rough-edge metadata was provided.")
    missing = [item["id"] for item in evidence["public_api"] if not item["docstring_present"]]
    body.extend(["", "## Analyzer findings", ""])
    if missing:
        body.extend(f"- Public API `{item_id}` has no docstring. Add a source docstring, regenerate, and rerun the completeness check." for item_id in missing)
    else:
        body.append("No missing public API docstrings were detected.")
    for error in evidence["parse_errors"]:
        body.append(f"- Could not parse `{error['path']}` at line {error['line']}: {error['message']}.")
    return _page("Troubleshooting", body)


def _onboarding(evidence: dict[str, Any]) -> str:
    body = ["## First steps", "", "- [ ] Read the concepts page and the module map."]
    body.extend(f"- [ ] Inspect `{item['path']}` and its public API docstrings." for item in evidence["modules"])
    if evidence["entry_points"]:
        body.extend(f"- [ ] Trace the `{entry['kind']}` entry point in `{entry['path']}`." for entry in evidence["entry_points"])
    body.extend(["- [ ] Review the API reference and add missing source docstrings.", "- [ ] Regenerate the docs and run the completeness check."])
    return _page("Onboarding Checklist", body)


SECTION_GENERATORS: dict[str, Callable[[dict[str, Any]], str]] = {
    "readme": _readme,
    "architecture": _architecture,
    "concepts": _concepts,
    "install": _install,
    "tutorials": _tutorials,
    "api_reference": _api_reference,
    "troubleshooting": _troubleshooting,
    "onboarding": _onboarding,
}


def generate_docs(evidence: dict[str, Any], out: str | Path) -> list[str]:
    """Write all documentation pages and diagram artifacts to ``out``."""
    if not evidence["repo"].get("is_synthetic_fixture"):
        raise ValueError("Documentation generation is limited to marked fictional synthetic fixtures.")
    destination = Path(out).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    evidence_path = destination / "evidence.json"
    evidence_path.write_text(evidence_json(evidence), encoding="utf-8", newline="\n")
    section_evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    written: list[str] = []
    for section, filename in SECTION_FILES.items():
        target = destination / filename
        target.write_text(SECTION_GENERATORS[section](section_evidence), encoding="utf-8", newline="\n")
        written.append(filename)
    written.append("evidence.json")
    (destination / "module-graph.txt").write_text(render_ascii(evidence), encoding="utf-8", newline="\n")
    (destination / "module-graph.svg").write_text(render_svg(evidence), encoding="utf-8", newline="\n")
    written.extend(["module-graph.txt", "module-graph.svg"])
    return written
