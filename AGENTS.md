# AGENTS.md

Guidance for coding agents working in `qgis_osminfo`.

## 1) Repository Overview

- Language: Python
- Project type: QGIS plugin (NextGIS OSMInfo)
- Domain: OpenStreetMap / Overpass / Nominatim integration in QGIS
- Package root: `src/osminfo`
- Build/tool entrypoint: `setup.py` (custom QGIS plugin builder)
- Lint/format/type config: `pyproject.toml` (`ruff`, `pyright`, `pytest`)
- Tests root: `tests/`
- Pre-commit config: `.pre-commit-config.yaml`

Key files:

- Plugin entry: `src/osminfo/__init__.py`
- Main plugin class: `src/osminfo/osminfo.py`
- Compatibility layer: `src/osminfo/compat.py`
- Logging: `src/osminfo/logging.py`
- Query builder: `src/osminfo/overpass/query_builder/query_builder.py`
- Wizard parser/compiler: `src/osminfo/overpass/query_builder/wizard/`
- Search UI/model: `src/osminfo/search/`
- Test harness and QGIS stubs: `tests/conftest.py`

## 2) Environment Expectations

- Runtime/plugin loading requires a Python environment where `qgis` imports work.
- Metadata declares `qgisMinimumVersion=3.22`, `qgisMaximumVersion=4.99`,
  `supportsQt6=True`.
- Compatibility target from `pyproject.toml`: Python 3.7.
- Many unit tests do not require a real QGIS runtime: `tests/conftest.py`
  injects lightweight `qgis` and `qgis.PyQt` stubs for wizard, query builder,
  and model tests.
- Commands related to resources and translations rely on Qt tooling in `PATH`,
  notably `pyrcc5`, `lrelease`, and `pylupdate5`.
- If Qt code must run headless, use `QT_QPA_PLATFORM=offscreen`.

## 3) Build / Bootstrap / Packaging

Primary help:

```bash
python setup.py --help
```

Supported top-level commands:

```bash
python setup.py bootstrap
python setup.py build
python setup.py install --qgis Vanilla --force
python setup.py uninstall --qgis Vanilla
python setup.py clean
python setup.py update_ts
python setup.py config vscode --qgis Vanilla
```

Bootstrap details:

```bash
python setup.py bootstrap
python setup.py bootstrap --qrc
python setup.py bootstrap --ts
```

Important bootstrap notes:

- `bootstrap` compiles resources and translations by default.
- `bootstrap --ui` exists in the CLI, but `[tool.qgspb.forms]` currently sets
  `compile = false`, so `.ui` files are shipped as raw UI files rather than
  generated Python modules.
- `src/osminfo/resources.py` is generated from `src/osminfo/resources.qrc` and
  should be regenerated, not hand-maintained.

Install/uninstall examples:

```bash
python setup.py install --qgis Vanilla --force
python setup.py install --qgis Vanilla --editable --force
python setup.py install --qgis VanillaFlatpak --force
python setup.py uninstall --qgis Vanilla --profile default
```

Notes:

- `install` and `uninstall` support `--qgis {Vanilla,VanillaFlatpak}`.
- `install` also supports `--profile`, `--editable`, and `--force`.
- `config vscode` generates local development helpers such as `.vscode/tasks.json`,
  `.vscode/launch.json`, and `.env`.
- `python setup.py build` creates `build/osminfo-<version>.zip`.

## 4) Lint / Format / Type Check

Preferred project command:

```bash
pre-commit run --all-files
```

Equivalent direct commands:

```bash
ruff check .
ruff check . --fix
ruff format .
pyright
```

Pre-commit currently runs:

- `addlicense` with `assets/license-header.txt` for Python files
- `check-toml`
- `ruff --fix`
- `ruff-format`

Notes:

- Keep line length at 79.
- Ruff target is `py37`.
- `src/osminfo/resources.py` is excluded from Ruff linting because it is generated.

## 5) Test Commands (Single-Test Focus)

Run full suite:

```bash
python -m pytest tests
```

Run a single file:

```bash
python -m pytest tests/test_query_builder.py
python -m pytest tests/wizard/test_parser.py
```

Run a single test function:

```bash
python -m pytest tests/test_query_builder.py::test_build_for_coords_accepts_qgs_point_xy
python -m pytest tests/wizard/test_parser.py::test_parse_regex_and_global_bounds
```

Useful selectors:

```bash
python -m pytest tests -k "query_builder"
python -m pytest tests -x -vv
```

Important test caveats:

- Current tests are mostly deterministic unit tests around query building,
  search completion, and wizard parsing/rendering.
- `tests/conftest.py` provides stubbed QGIS and Qt modules, so keep new tests at
  that level when possible.
- Avoid adding tests that depend on live Overpass or Nominatim endpoints unless
  explicitly required.

## 6) Cursor / Copilot Rules Check

Repository scan found:

- No `.cursorrules`
- No `.cursor/rules/`
- No `.github/copilot-instructions.md`

If these files appear later, treat them as high-priority constraints and update
this document.

## 7) Code Style Guidelines

### Imports

- Order imports as: stdlib -> third-party/QGIS/Qt -> local package imports.
- Prefer explicit imports over wildcard imports.
- Import Qt only from `qgis.PyQt`, never from `PyQt5` directly.

### Formatting

- Follow Ruff formatting and linting configuration from `pyproject.toml`.
- Respect the 79-character limit.
- Preserve existing file structure and avoid unrelated refactors.

### Types and Annotations

- Add type hints for new or changed public APIs and non-trivial internals.
- Keep annotations compatible with Python 3.7.
- Use narrow `pyright: ignore[...]` comments only when needed for QGIS typing gaps.

### Naming

- Functions, variables, modules: `snake_case`
- Classes, exceptions, enums: `PascalCase`
- Constants: `UPPER_SNAKE_CASE`
- When overriding Qt/QGIS APIs, preserve the expected camelCase method names.

### Error Handling

- Prefer early returns for guard conditions.
- Keep user-facing messages short and actionable.
- Preserve exception causes with `raise ... from error` where helpful.

### Logging

- Use the logging helpers from `src/osminfo/logging.py`.
- Prefer logger-based diagnostics over `print()` in plugin code.
- Use debug logging for operational detail and warnings/errors for user-impacting failures.

### QGIS / Qt Compatibility

- Respect compatibility shims in `src/osminfo/compat.py`.
- Do not remove version guards without checking the QGIS 3.22 to 4.99 support range.
- Be careful with Qt5/Qt6 differences, especially around moved Qt classes.

### UI / Resources / Translations

- Keep `.ui` files under `ui` subfolder unless there is a strong reason to move them.
- `.ui` files are packaged directly; do not assume generated Python UI modules exist.
- Regenerate resources and translations through `setup.py` instead of editing generated outputs manually.
- Keep `metadata.txt`, `pyproject.toml`, and packaged resource paths aligned.

### Tests

- Prefer narrow regression tests near the affected subsystem.
- For wizard/query changes, add or update pure pytest tests before considering integration coverage.
- Keep tests isolated and deterministic.

## 8) Agent Workflow Checklist

- Make minimal, task-scoped changes.
- Check whether the target file is generated before editing it.
- Run focused tests first, then broader checks if the change warrants it.
- Run `pre-commit run --all-files` for substantial Python changes.
- Do not commit generated caches such as `__pycache__`, `.pytest_cache`, or `.ruff_cache`.
- Preserve existing public behavior unless the task explicitly requires changing it.
