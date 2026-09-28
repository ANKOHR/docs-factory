# Docs Factory

Docs Factory is a deterministic documentation generator built around Python static analysis. It parses source modules with `ast`, maps internal imports, detects entry points, extracts top-level public functions and classes, and reports docstring coverage. Template generators use that evidence to write a complete documentation set and a completeness report.

The supported documentation demo targets are fictional repositories created by the fixture generator. Source analysis can inspect a Python repository, but documentation generation, diagrams, and CLI completeness reports require an intact generated synthetic fixture.

## Quickstart

Use Python 3.10 or newer. Runtime code uses only the Python standard library. Install pytest to run the suite.

```console
python -m pip install pytest
python -m pip install -e .
df fixtures --out .\examples
df analyse .\examples\task_runner
df generate .\examples\task_runner --out .\examples\task_runner\docs
df diagram .\examples\task_runner
df check .\examples\task_runner .\examples\task_runner\docs --threshold 80
python -m pytest
```

The planted missing API item means a completeness check at 100 percent exits with status 1 until that item is documented. Use `python -m docs_factory` in place of `df` when the console script is not installed. Fixtures are created locally; there are no downloads and no real project is cloned.

## HONESTY BOUNDARY

Docs Factory generates documentation only for fictional synthetic fixture repositories, never for real open-source projects. It reads Python source with static analysis and fills deterministic templates from that evidence. No language model writes the prose. No real project has been documented by this tool. The generated pages and diagrams repeat this boundary so that a reader can distinguish fixture documentation from documentation of a real project.

## Architecture

```text
Python source files
        |
        v
  ast analyser ----> JSON evidence ----> deterministic section templates
        |                                      |    |    |    |
        +----> import graph ----> ASCII and SVG     docs pages
                                               completeness checker
```

The analyser walks Python files in sorted path order. The evidence records modules, internal import edges, detected entry points, public API signatures and decorators, source docstrings, per-module docstring coverage, parse errors, and fixture rough-edge metadata. Section generators read the evidence object saved as `evidence.json`. The checker parses stable API markers in `api-reference.md`, compares them with the current extracted API, and reports missing and removed items.

### Determinism

Iteration and output are sorted lexicographically. The documented determinism seed is `0`; the current implementation does not use random ordering. Evidence and generated documentation contain no generation timestamps. Audit records do include UTC timestamps and are kept separately in `df-audit.jsonl`.

## Analyser evidence schema

The JSON file has `schema_version: 1` and these top-level fields:

- `repo`: resolved path, name, and synthetic fixture status and metadata.
- `modules`: module path, module docstring, internal imports, and public API docstring coverage.
- `import_edges`: sorted `{from, to}` module relationships.
- `entry_points`: `main` functions, `if __name__ == "__main__"` guards, `@cli_entrypoint` markers, and `# docs-factory: cli` script markers.
- `public_api`: top-level public functions and classes with stable ID, kind, signature, decorators, docstring, path, and line.
- `docstring_coverage`: aggregate and per-module counts and percentages for public API docstrings.
- `parse_errors`: Python files that could not be parsed, with path, line, and parser message.
- `honesty_boundary` and `determinism`: scope statement and fixed ordering metadata.

## Generated section catalogue

`df generate REPO --out DIR` writes the evidence JSON, these Markdown sections, deterministic diagrams, and `completeness-report.json`:

| Output | What it contains |
| --- | --- |
| `README.md` | Fixture purpose, install hint, detected quickstart entry points, and a text module graph. |
| `architecture.md` | Module summaries, dependency edges, and a text graph. |
| `concepts.md` | Module concepts taken from source module docstrings. |
| `install.md` | Python requirement, local install command, and detected entry points. |
| `tutorials.md` | Tutorials anchored to parsed entry points and a documented public function. |
| `api-reference.md` | Extracted signatures and source docstrings, with missing-docstring items called out separately. |
| `troubleshooting.md` | Fixture rough-edge metadata, missing API docstrings, and parse failures. |
| `onboarding.md` | A checklist based on the analyzed modules and entry points. |
| `module-graph.txt`, `module-graph.svg` | Sorted dependency graph with module docstring coverage labels. |
| `evidence.json`, `completeness-report.json` | Machine-readable analyzer evidence and API coverage results. |

## CLI

- `df fixtures --out DIR`: generate two fictional, synthetic Python repositories.
- `df analyse REPO [--out FILE]`: write the AST-derived JSON evidence.
- `df generate REPO --out DIR [--threshold PERCENT]`: write all documentation for a marked fixture and include its completeness report.
- `df diagram REPO [--out-dir DIR]`: print the ASCII graph and write the matching SVG for a marked fixture.
- `df check REPO DOCS [--threshold PERCENT] [--out FILE]`: compare API reference markers with current public API. The command exits non-zero below the threshold.

Each command appends an audit record with its command, repository path, generated sections, evidence hash, completeness result when available, and UTC timestamp. `df-audit.jsonl` is ignored by Git.

## Tests

Run `python -m pytest`. The suite covers deterministic fixtures and docs, AST evidence, templates, diagrams, completeness gaps and removed API items, CLI commands, audit records, and end-to-end generation for both synthetic repos.
