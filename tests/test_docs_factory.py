from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from docs_factory.analyzer import analyse_repository, evidence_json
from docs_factory.checker import check_completeness
from docs_factory.constants import HONESTY_BOUNDARY
from docs_factory.diagrams import render_ascii, render_svg
from docs_factory.fixtures import generate_fixtures
from docs_factory.generators import SECTION_FILES, generate_docs

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def fixture_repos(tmp_path: Path) -> dict[str, Path]:
    roots = generate_fixtures(tmp_path / "fixtures")
    return {path.name: path for path in roots}


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _cli(*args: str, cwd: Path = PROJECT_ROOT) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "docs_factory", *args],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_fixture_generation_is_deterministic_and_contains_planted_api(tmp_path: Path) -> None:
    first = {path.name: path for path in generate_fixtures(tmp_path / "first")}
    second = {path.name: path for path in generate_fixtures(tmp_path / "second")}
    assert set(first) == {"task_runner", "config_service"}
    for name in sorted(first):
        assert _snapshot(first[name]) == _snapshot(second[name])
        marker = json.loads((first[name] / ".docs-factory-fixture.json").read_text(encoding="utf-8"))
        assert marker["synthetic"] is True
        assert "Fictional" in (first[name] / "README.md").read_text(encoding="utf-8")
        assert "no language model" in (first[name] / "README.md").read_text(encoding="utf-8").lower()

    task_api = {item["id"] for item in analyse_repository(first["task_runner"])["public_api"]}
    config_api = {item["id"] for item in analyse_repository(first["config_service"])["public_api"]}
    assert "taskrunner.engine.retry_task" in task_api
    assert "configservice.settings.validate_overrides" in config_api


def test_analyser_matches_task_runner_expectations_and_is_byte_stable(fixture_repos: dict[str, Path]) -> None:
    root = fixture_repos["task_runner"]
    first = analyse_repository(root)
    second = analyse_repository(root)
    assert evidence_json(first).encode("utf-8") == evidence_json(second).encode("utf-8")
    assert [item["name"] for item in first["modules"]] == [
        "taskrunner",
        "taskrunner.__main__",
        "taskrunner.cli",
        "taskrunner.engine",
        "taskrunner.marked_report",
        "taskrunner.store",
        "taskrunner.tasks",
    ]
    assert {(edge["from"], edge["to"]) for edge in first["import_edges"]} == {
        ("taskrunner", "taskrunner.engine"),
        ("taskrunner", "taskrunner.tasks"),
        ("taskrunner.__main__", "taskrunner.cli"),
        ("taskrunner.cli", "taskrunner.engine"),
        ("taskrunner.engine", "taskrunner.store"),
        ("taskrunner.engine", "taskrunner.tasks"),
        ("taskrunner.store", "taskrunner.tasks"),
        ("taskrunner.tasks", "taskrunner.engine"),
    }
    assert {(item["module"], item["kind"], item["name"]) for item in first["entry_points"]} == {
        ("taskrunner.__main__", "main_guard", "__main__"),
        ("taskrunner.cli", "main_function", "main"),
        ("taskrunner.cli", "marked_cli", "main"),
        ("taskrunner.marked_report", "marked_cli_script", "marked_report"),
    }
    api = {item["id"]: item for item in first["public_api"]}
    assert set(api) == {
        "taskrunner.cli.cli_entrypoint",
        "taskrunner.cli.main",
        "taskrunner.engine.retry_task",
        "taskrunner.engine.run_tasks",
        "taskrunner.marked_report.report_main",
        "taskrunner.store.TaskStore",
        "taskrunner.tasks.Task",
    }
    assert api["taskrunner.engine.run_tasks"]["signature"] == "run_tasks(names: list[str]) -> list[str]"
    assert api["taskrunner.cli.main"]["decorators"] == ["cli_entrypoint"]
    assert api["taskrunner.engine.retry_task"]["docstring_present"] is False
    assert first["docstring_coverage"]["documented"] == 6
    assert first["docstring_coverage"]["total"] == 7


def test_analyser_matches_config_service_expectations(fixture_repos: dict[str, Path]) -> None:
    evidence = analyse_repository(fixture_repos["config_service"])
    assert [item["name"] for item in evidence["modules"]] == [
        "configservice",
        "configservice.__main__",
        "configservice.cli",
        "configservice.loader",
        "configservice.marked_admin",
        "configservice.settings",
    ]
    assert {(edge["from"], edge["to"]) for edge in evidence["import_edges"]} == {
        ("configservice", "configservice.loader"),
        ("configservice", "configservice.settings"),
        ("configservice.__main__", "configservice.cli"),
        ("configservice.cli", "configservice.loader"),
        ("configservice.loader", "configservice.settings"),
        ("configservice.settings", "configservice.loader"),
    }
    assert {(item["module"], item["kind"]) for item in evidence["entry_points"]} == {
        ("configservice.__main__", "main_guard"),
        ("configservice.cli", "main_function"),
        ("configservice.marked_admin", "marked_cli_script"),
    }
    assert {item["id"] for item in evidence["public_api"]} == {
        "configservice.cli.main",
        "configservice.loader.load_settings",
        "configservice.marked_admin.admin_main",
        "configservice.settings.Settings",
        "configservice.settings.validate_overrides",
    }
    assert evidence["public_api"][-1]["docstring_present"] is False
    assert evidence["docstring_coverage"]["percent"] == 80.0


def test_analyser_records_syntax_errors(tmp_path: Path) -> None:
    (tmp_path / "broken.py").write_text("def broken(:\n    pass\n", encoding="utf-8")
    evidence = analyse_repository(tmp_path)
    assert evidence["parse_errors"] == [
        {"line": 1, "message": "invalid syntax", "path": "broken.py"}
    ]


@pytest.mark.parametrize("fixture_name", ["task_runner", "config_service"])
def test_all_generated_sections_are_deterministic_and_evidence_derived(
    tmp_path: Path, fixture_repos: dict[str, Path], fixture_name: str
) -> None:
    evidence = analyse_repository(fixture_repos[fixture_name])
    first = tmp_path / f"{fixture_name}-docs-one"
    second = tmp_path / f"{fixture_name}-docs-two"
    written = generate_docs(evidence, first)
    assert generate_docs(evidence, second) == written
    assert _snapshot(first) == _snapshot(second)
    assert set(SECTION_FILES.values()).issubset(written)

    for filename in SECTION_FILES.values():
        page = (first / filename).read_text(encoding="utf-8")
        assert "HONESTY BOUNDARY" in page
        assert "no language model" in page.lower()
        assert "No real open-source project" in page
    assert fixture_name in (first / "README.md").read_text(encoding="utf-8")
    assert evidence["entry_points"][0]["module"] in (first / "tutorials.md").read_text(encoding="utf-8")
    assert evidence["modules"][0]["docstring"] in (first / "concepts.md").read_text(encoding="utf-8")
    assert evidence["import_edges"][0]["from"] in (first / "architecture.md").read_text(encoding="utf-8")
    assert evidence["public_api"][0]["signature"] in (first / "api-reference.md").read_text(encoding="utf-8")
    missing_id = (
        "taskrunner.engine.retry_task"
        if fixture_name == "task_runner"
        else "configservice.settings.validate_overrides"
    )
    assert missing_id in (first / "troubleshooting.md").read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("fixture_name", "expected_missing"),
    [
        ("task_runner", ["taskrunner.engine.retry_task"]),
        ("config_service", ["configservice.settings.validate_overrides"]),
    ],
)
def test_checker_reports_only_planted_undocumented_api(
    tmp_path: Path,
    fixture_repos: dict[str, Path],
    fixture_name: str,
    expected_missing: list[str],
) -> None:
    evidence = analyse_repository(fixture_repos[fixture_name])
    docs = tmp_path / f"{fixture_name}-docs"
    generate_docs(evidence, docs)
    report = check_completeness(evidence, docs, threshold=0)
    assert report["undocumented_items"] == expected_missing
    assert report["removed_items"] == []
    assert report["items"]
    assert report["docstring_coverage"]["total"] == len(evidence["public_api"])
    assert report["passed"] is True
    strict = check_completeness(evidence, docs, threshold=100)
    assert strict["passed"] is False


def test_checker_reports_documented_but_removed_item_on_tampered_copy(
    tmp_path: Path, fixture_repos: dict[str, Path]
) -> None:
    original = fixture_repos["task_runner"]
    docs = tmp_path / "original-docs"
    generate_docs(analyse_repository(original), docs)
    tampered = tmp_path / "tampered-task-runner"
    shutil.copytree(original, tampered)
    engine = tampered / "taskrunner" / "engine.py"
    engine.write_text(
        engine.read_text(encoding="utf-8").replace("def run_tasks(", "def _run_tasks("),
        encoding="utf-8",
    )
    report = check_completeness(analyse_repository(tampered), docs, threshold=0)
    assert report["removed_items"] == ["taskrunner.engine.run_tasks"]
    assert "taskrunner.engine.run_tasks" not in report["undocumented_items"]


def test_diagram_output_is_deterministic_and_lists_expected_edges(
    tmp_path: Path, fixture_repos: dict[str, Path]
) -> None:
    evidence = analyse_repository(fixture_repos["task_runner"])
    svg = render_svg(evidence)
    assert svg == render_svg(analyse_repository(fixture_repos["task_runner"]))
    first = tmp_path / "graph-one"
    second = tmp_path / "graph-two"
    assert _cli("diagram", str(fixture_repos["task_runner"]), "--out-dir", str(first)).returncode == 0
    assert _cli("diagram", str(fixture_repos["task_runner"]), "--out-dir", str(second)).returncode == 0
    assert (first / "module-graph.svg").read_bytes() == (second / "module-graph.svg").read_bytes()
    graph = render_ascii(evidence)
    assert "taskrunner.tasks -> taskrunner.engine" in graph
    assert "taskrunner.engine -> taskrunner.store" in graph
    assert "HONESTY BOUNDARY" not in graph
    assert "no language model writes the prose" in graph.lower()


def test_generator_rejects_unmarked_repository(tmp_path: Path) -> None:
    (tmp_path / "module.py").write_text('"""A local module."""\n', encoding="utf-8")
    evidence = analyse_repository(tmp_path)
    with pytest.raises(ValueError, match="marked fictional synthetic fixtures"):
        generate_docs(evidence, tmp_path / "docs")

    spoofed = tmp_path / "spoofed"
    spoofed.mkdir()
    (spoofed / "other.py").write_text('"""An unrelated module."""\n', encoding="utf-8")
    (spoofed / ".docs-factory-fixture.json").write_text(
        json.dumps({"synthetic": True, "generated_by": "Docs Factory", "name": "task_runner"}),
        encoding="utf-8",
    )
    spoofed_evidence = analyse_repository(spoofed)
    assert spoofed_evidence["repo"]["is_synthetic_fixture"] is False


def test_end_to_end_generation_for_both_fixtures(tmp_path: Path) -> None:
    fixtures = {path.name: path for path in generate_fixtures(tmp_path / "examples")}
    for name, repo in sorted(fixtures.items()):
        docs = tmp_path / "built-docs" / name
        generated = _cli("generate", str(repo), "--out", str(docs), "--threshold", "0")
        assert generated.returncode == 0, generated.stderr
        output = json.loads(generated.stdout)
        assert output["command"] == "generate"
        assert output["completeness_result"]["undocumented_items"]
        assert (docs / "completeness-report.json").is_file()
        for filename in SECTION_FILES.values():
            page = (docs / filename).read_text(encoding="utf-8")
            assert "HONESTY BOUNDARY" in page
        assert "no language model" in (docs / "module-graph.svg").read_text(encoding="utf-8").lower()
        assert "no language model" in (docs / "module-graph.txt").read_text(encoding="utf-8").lower()


def test_cli_smoke_for_each_subcommand_and_audit_trail(tmp_path: Path) -> None:
    fixtures_out = tmp_path / "cli-fixtures"
    made = _cli("fixtures", "--out", str(fixtures_out))
    assert made.returncode == 0, made.stderr
    assert HONESTY_BOUNDARY in made.stdout
    fixture = fixtures_out / "task_runner"

    evidence_path = tmp_path / "cli-evidence.json"
    analysed = _cli("analyse", str(fixture), "--out", str(evidence_path))
    assert analysed.returncode == 0, analysed.stderr
    assert json.loads(evidence_path.read_text(encoding="utf-8"))["public_api"]

    docs = tmp_path / "cli-docs"
    generated = _cli("generate", str(fixture), "--out", str(docs), "--threshold", "0")
    assert generated.returncode == 0, generated.stderr

    diagram_dir = tmp_path / "cli-diagrams"
    diagram = _cli("diagram", str(fixture), "--out-dir", str(diagram_dir))
    assert diagram.returncode == 0, diagram.stderr
    assert "taskrunner.tasks -> taskrunner.engine" in diagram.stdout
    assert "no language model" in diagram.stdout.lower()
    assert (diagram_dir / "module-graph.svg").is_file()

    report_path = tmp_path / "cli-check.json"
    checked = _cli("check", str(fixture), str(docs), "--threshold", "0", "--out", str(report_path))
    assert checked.returncode == 0, checked.stderr
    assert json.loads(report_path.read_text(encoding="utf-8"))["passed"] is True

    audit_path = fixture / "df-audit.jsonl"
    records = [json.loads(line) for line in audit_path.read_text(encoding="utf-8").splitlines()]
    assert [record["command"] for record in records] == ["analyse", "generate", "diagram", "check"]
    for record in records:
        assert record["repo_path"] == str(fixture.resolve())
        assert record["evidence_hash"]
        assert record["timestamp"].endswith("Z")
        assert isinstance(record["sections_generated"], list)
    assert records[-1]["completeness_result"]["passed"] is True
    fixture_audit = [json.loads(line) for line in (fixtures_out / "df-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert fixture_audit[0]["command"] == "fixtures"
    assert fixture_audit[0]["evidence_hash"]


def test_cli_check_exits_nonzero_below_threshold(tmp_path: Path) -> None:
    repo = generate_fixtures(tmp_path / "threshold-fixtures")[1]
    docs = tmp_path / "threshold-docs"
    generate_docs(analyse_repository(repo), docs)
    result = _cli("check", str(repo), str(docs), "--threshold", "100")
    assert result.returncode == 1
    assert json.loads(result.stdout)["passed"] is False


def test_analysis_is_allowed_but_cli_generation_is_fixture_only(tmp_path: Path) -> None:
    repo = tmp_path / "ordinary-repo"
    repo.mkdir()
    (repo / "sample.py").write_text('"""A sample module."""\n', encoding="utf-8")
    result = _cli("generate", str(repo), "--out", str(tmp_path / "ordinary-docs"))
    assert result.returncode == 2
    assert "limited to marked fictional synthetic fixtures" in result.stderr
    assert "No real open-source project" in result.stderr
    audit = [json.loads(line) for line in (repo / "df-audit.jsonl").read_text(encoding="utf-8").splitlines()]
    assert audit[-1]["command"] == "generate"
    assert audit[-1]["evidence_hash"] is None
