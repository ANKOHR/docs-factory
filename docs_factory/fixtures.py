"""Deterministic generators for the fictional demonstration repositories."""

from __future__ import annotations

import json
from pathlib import Path

from .constants import TOOL_NAME

FIXTURE_FILES: dict[str, dict[str, str]] = {
    "task_runner": {
        "README.md": "# Fictional Task Runner\n\nSynthetic Docs Factory fixture. This fictional source tree exists only for testing static analysis and documentation generation. Docs Factory reads static evidence and fills deterministic templates; no language model writes prose. No real open-source project has been documented by this tool.\n",
        ".docs-factory-fixture.json": "",  # Filled from stable metadata below.
        "taskrunner/__init__.py": '"""A fictional package for running small named tasks."""\n\nfrom .engine import run_tasks\nfrom .tasks import Task\n\n__all__ = ["Task", "run_tasks"]\n',
        "taskrunner/__main__.py": '"""Module entry point for the fictional task runner."""\n\nfrom .cli import main\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n',
        "taskrunner/cli.py": '"""Command line interface for the fictional task runner."""\n\nfrom .engine import run_tasks\n\n\ndef cli_entrypoint(function):\n    """Mark a function as a command line entry point."""\n    return function\n\n\n@cli_entrypoint\ndef main() -> int:\n    """Run the sample task list and return a process status."""\n    run_tasks(["prepare", "report"])\n    return 0\n',
        "taskrunner/engine.py": '"""Run task objects in order."""\n\nfrom .store import TaskStore\nfrom .tasks import Task\n\n\ndef run_tasks(names: list[str]) -> list[str]:\n    """Run each named task and return its completion messages."""\n    store = TaskStore()\n    return [store.run(Task(name)) for name in names]\n\n\ndef retry_task(name: str, attempts: int = 2) -> str:\n    return f"retried {name} {attempts} times"\n',
        "taskrunner/marked_report.py": '# docs-factory: cli\n"""Marked command line report script for the fictional task runner."""\n\n\ndef report_main() -> int:\n    """Print the sample report and return a process status."""\n    return 0\n',
        "taskrunner/store.py": '"""Keep an in-memory record of completed tasks."""\n\nfrom .tasks import Task\n\n\nclass TaskStore:\n    """Run tasks and keep their completion messages."""\n\n    def run(self, task: Task) -> str:\n        """Return a stable completion message for a task."""\n        return f"completed {task.name}"\n',
        "taskrunner/tasks.py": '"""Define the task value used by the runner."""\n\nfrom typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from .engine import run_tasks\n\n\nclass Task:\n    """A named unit of work for the fictional runner."""\n\n    def __init__(self, name: str) -> None:\n        """Create a task with its display name."""\n        self.name = name\n',
    },
    "config_service": {
        "README.md": "# Fictional Config Service\n\nSynthetic Docs Factory fixture. This fictional source tree demonstrates a small configuration-driven service. Docs Factory reads static evidence and fills deterministic templates; no language model writes prose. No real open-source project has been documented by this tool.\n",
        ".docs-factory-fixture.json": "",
        "configservice/__init__.py": '"""A fictional configuration-driven service."""\n\nfrom .loader import load_settings\nfrom .settings import Settings\n\n__all__ = ["Settings", "load_settings"]\n',
        "configservice/__main__.py": '"""Module entry point for the fictional config service."""\n\nfrom .cli import main\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n',
        "configservice/cli.py": '"""Command line interface for the fictional config service."""\n\nfrom .loader import load_settings\n\n\ndef main() -> int:\n    """Load the sample configuration and return a process status."""\n    load_settings({"name": "demo", "port": 8000})\n    return 0\n',
        "configservice/loader.py": '"""Load settings from a mapping of configuration values."""\n\nfrom .settings import Settings, validate_overrides\n\n\ndef load_settings(values: dict[str, object]) -> Settings:\n    """Validate a mapping and create a settings object."""\n    validate_overrides(values)\n    return Settings(**values)\n',
        "configservice/marked_admin.py": '# docs-factory: cli\n"""Marked command line admin script for the fictional config service."""\n\n\ndef admin_main() -> int:\n    """Run the sample admin action and return a process status."""\n    return 0\n',
        "configservice/settings.py": '"""Configuration values used by the fictional service."""\n\nfrom typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from .loader import load_settings\n\n\nclass Settings:\n    """Store the service name and port."""\n\n    def __init__(self, name: str, port: int = 8000) -> None:\n        """Create service settings."""\n        self.name = name\n        self.port = port\n\n\ndef validate_overrides(values: dict[str, object]) -> None:\n    if "port" in values and not isinstance(values["port"], int):\n        raise ValueError("port must be an integer")\n',
    },
}

ROUGH_EDGES = {
    "task_runner": [
        "A TYPE_CHECKING-only import points from taskrunner.tasks back to taskrunner.engine, forming a circular-ish static dependency.",
        "taskrunner.engine.retry_task is a planted public API item with no docstring.",
    ],
    "config_service": [
        "A TYPE_CHECKING-only import points from configservice.settings back to configservice.loader, forming a circular-ish static dependency.",
        "configservice.settings.validate_overrides is a planted public API item with no docstring.",
    ],
}


def _fixture_metadata(name: str) -> str:
    data = {
        "generated_by": TOOL_NAME,
        "name": name,
        "rough_edges": ROUGH_EDGES[name],
        "synthetic": True,
        "version": 1,
    }
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def verify_fixture(root: str | Path, name: str) -> bool:
    """Confirm the marker and Python source match one canonical generated fixture."""
    if name not in FIXTURE_FILES:
        return False
    fixture_root = Path(root)
    expected_python: set[str] = set()
    for relative, source in FIXTURE_FILES[name].items():
        if relative == ".docs-factory-fixture.json":
            source = _fixture_metadata(name)
        if relative.endswith(".py"):
            expected_python.add(relative)
        target = fixture_root / relative
        try:
            if target.read_text(encoding="utf-8") != source:
                return False
        except OSError:
            return False
    actual_python = {
        path.relative_to(fixture_root).as_posix()
        for path in fixture_root.rglob("*.py")
        if not any(part in {".git", ".venv", "venv", "__pycache__"} for part in path.relative_to(fixture_root).parts)
    }
    return actual_python == expected_python


def generate_fixtures(out: str | Path) -> list[Path]:
    """Write both fictional fixture repositories in stable path order."""
    destination = Path(out).expanduser().resolve()
    destination.mkdir(parents=True, exist_ok=True)
    created: list[Path] = []
    for fixture_name in sorted(FIXTURE_FILES):
        fixture_root = destination / fixture_name
        fixture_root.mkdir(parents=True, exist_ok=True)
        for relative, content in sorted(FIXTURE_FILES[fixture_name].items()):
            if relative == ".docs-factory-fixture.json":
                content = _fixture_metadata(fixture_name)
            target = fixture_root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
        created.append(fixture_root)
    return created
