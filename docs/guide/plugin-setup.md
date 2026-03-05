# Plugin Environment Setup

## How plugins run

Plugins (`konkon.py`) are loaded into the **host Python process** via `importlib`. There is no sandbox or isolated runtime — any `import` in your plugin resolves against the same Python environment that runs `konkon`.

This means:

- If your plugin only uses the standard library and `konkon.types`, no extra setup is needed.
- If your plugin imports external libraries (e.g. `requests`, `openai`), those libraries **must be installed** in the environment where `konkon` runs.

## Setup for plugins with external dependencies

### Option 1: uv project (recommended)

Create a `pyproject.toml` in your plugin directory:

```toml
[project]
name = "my-konkon-plugin"
requires-python = ">=3.11"
dependencies = [
    "konkondb",
    "requests",
    "openai",
]
```

Then run konkon via `uv run`:

```bash
cd my-plugin-dir/
uv sync              # create venv and install all dependencies
uv run konkon build
uv run konkon search "" -p view=default
```

`uv run` automatically manages the virtual environment. No manual activation required.

### Option 2: manual venv

```bash
cd my-plugin-dir/
python -m venv .venv
source .venv/bin/activate
pip install konkondb requests openai
konkon build
konkon search "" -p view=default
```

### Option 3: global install (no external dependencies)

If your plugin only depends on libraries already bundled with konkondb, a global install is sufficient:

```bash
pip install konkondb
konkon build
```

No venv or project setup needed.

## Notes

- `uv sync` does **not** remove packages that were installed separately. You can `uv pip install` additional packages into the same venv.
- Avoid `uv sync --exact` if you have manually installed packages — it removes anything not in `pyproject.toml`.
