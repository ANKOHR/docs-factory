"""Append one machine-readable record for each CLI invocation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def append_audit(
    repo: str | Path,
    command: str,
    sections: list[str],
    evidence_hash: str | None,
    completeness_result: dict[str, Any] | None = None,
) -> None:
    root = Path(repo).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    record = {
        "command": command,
        "repo_path": str(root),
        "sections_generated": sorted(sections),
        "evidence_hash": evidence_hash,
        "completeness_result": completeness_result,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
    }
    with (root / "df-audit.jsonl").open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
