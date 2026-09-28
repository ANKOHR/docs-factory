"""Fixed-layout text and SVG renderers for module dependency evidence."""

from __future__ import annotations

from html import escape
from typing import Any

from .constants import HONESTY_BOUNDARY


def render_ascii(evidence: dict[str, Any]) -> str:
    modules = sorted(evidence["modules"], key=lambda item: item["name"])
    edges = sorted(evidence["import_edges"], key=lambda item: (item["from"], item["to"]))
    lines = ["Fictional synthetic fixture module graph", HONESTY_BOUNDARY, "", "Modules:"]
    for module in modules:
        coverage = module["coverage"]["percent"]
        lines.append(f"  {module['name']} [{coverage:.1f}% docstring coverage]")
    lines.extend(["", "Imports:"])
    lines.extend(f"  {edge['from']} -> {edge['to']}" for edge in edges)
    if not edges:
        lines.append("  (no internal imports)")
    return "\n".join(lines) + "\n"


def render_svg(evidence: dict[str, Any]) -> str:
    modules = sorted(evidence["modules"], key=lambda item: item["name"])
    edges = sorted(evidence["import_edges"], key=lambda item: (item["from"], item["to"]))
    width = 720
    top = 92
    row_height = 82
    height = max(210, top + len(modules) * row_height + 38)
    y_for = {module["name"]: top + index * row_height + 25 for index, module in enumerate(modules)}
    body: list[str] = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f"  <title>Fictional synthetic fixture module graph</title>",
        f"  <desc>{escape(HONESTY_BOUNDARY)}</desc>",
        '  <defs><marker id="arrow" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0,0 L10,4 L0,8 z" fill="#64748b"/></marker></defs>',
        '  <rect width="100%" height="100%" fill="#ffffff"/>',
        '  <text x="24" y="32" font-family="sans-serif" font-size="18" font-weight="700" fill="#0f172a">Module dependency graph</text>',
        '  <text x="24" y="56" font-family="sans-serif" font-size="11" fill="#475569">Static AST evidence for a fictional synthetic fixture</text>',
    ]
    for edge in edges:
        if edge["from"] not in y_for or edge["to"] not in y_for:
            continue
        start_y, end_y = y_for[edge["from"]] + 17, y_for[edge["to"]] + 17
        body.append(
            f'  <path d="M 420 {start_y} C 520 {start_y}, 520 {end_y}, 420 {end_y}" fill="none" stroke="#64748b" stroke-width="1.5" marker-end="url(#arrow)"/>'
        )
    for module in modules:
        y = y_for[module["name"]]
        coverage = module["coverage"]["percent"]
        label = escape(module["name"])
        body.extend(
            [
                f'  <rect x="24" y="{y}" width="396" height="36" rx="6" fill="#eff6ff" stroke="#2563eb"/>',
                f'  <text x="38" y="{y + 23}" font-family="monospace" font-size="13" fill="#0f172a">{label}</text>',
                f'  <text x="402" y="{y + 23}" text-anchor="end" font-family="sans-serif" font-size="11" fill="#334155">{coverage:.1f}% documented</text>',
            ]
        )
    body.append("</svg>")
    return "\n".join(body) + "\n"
