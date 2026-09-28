"""Cross-reference generated API documentation against current AST evidence."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

API_MARKER = re.compile(r"^<!-- df-api: ([A-Za-z_][A-Za-z0-9_.]*) -->$", re.MULTILINE)


def check_completeness(
    evidence: dict[str, Any], docs_dir: str | Path, threshold: float = 100.0
) -> dict[str, Any]:
    if not 0.0 <= threshold <= 100.0:
        raise ValueError("Threshold must be between 0 and 100.")
    reference = Path(docs_dir) / "api-reference.md"
    if not reference.is_file():
        raise ValueError(f"API reference not found: {reference}")
    text = reference.read_text(encoding="utf-8")
    documented_ids = set(API_MARKER.findall(text))
    actual = {item["id"]: item for item in evidence["public_api"]}
    items: list[dict[str, Any]] = []
    for item_id in sorted(actual):
        items.append(
            {
                "id": item_id,
                "status": "documented" if item_id in documented_ids else "undocumented",
                "docstring_present": actual[item_id]["docstring_present"],
            }
        )
    removed_ids = sorted(documented_ids - set(actual))
    items.extend({"id": item_id, "status": "removed", "docstring_present": None} for item_id in removed_ids)
    documented_count = sum(item_id in documented_ids for item_id in actual)
    total = len(actual)
    coverage = round(100.0 * documented_count / total, 1) if total else 100.0
    return {
        "schema_version": 1,
        "repo": evidence["repo"]["name"],
        "honesty_boundary": evidence["honesty_boundary"],
        "threshold": threshold,
        "coverage_percent": coverage,
        "documented_count": documented_count,
        "public_api_count": total,
        "undocumented_items": sorted(set(actual) - documented_ids),
        "removed_items": removed_ids,
        "items": items,
        "docstring_coverage": evidence["docstring_coverage"],
        "passed": coverage >= threshold,
    }
