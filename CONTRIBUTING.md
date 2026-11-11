# Contributing to GhostRun

GhostRun is a standalone Hermes plugin. Keep `plugin.yaml` and `__init__.py` at the repository root so Hermes can discover it.

## Local checks

Use Python 3.12 and [uv](https://docs.astral.sh/uv/). From the repository root:

```bash
uv run --no-project --with-requirements requirements-dev.txt python -m pytest tests --ignore=tests/integration -q
```

These CPU unit tests need neither Hermes nor CUDA. GitHub Actions runs the same command on pushes and pull requests.

To load a source checkout in an existing Hermes installation, from the repository root:

```bash
mkdir -p "$HOME/.hermes/plugins"
ln -s "$(pwd)" "$HOME/.hermes/plugins/ghostrun"
hermes plugins enable ghostrun
hermes plugins validate .
```

For GPU training, install `requirements-runtime.txt` into a separate runtime with CUDA support and point the plugin's `python` setting at that interpreter. See [GPU engine](docs/GPU_ENGINE.md).

The [integration harness](tests/integration/hermes_itest.py) documents its additional Hermes, emulator and runtime setup. Engine tests under `engine/rl/tests/` have separate compiler, GPU or game requirements; they are not part of the CPU CI job.

## Where changes belong

- `__init__.py` and `plugin.yaml`: Hermes registration and plugin metadata.
- `core/`: stage commands, training control, watcher, oracle and comparison tools.
- `engine/`: training, reward readers and emulator integration.
- `skills/`: the six agent workflows.
- `tests/`: unit tests, generated fixtures and the Hermes integration harness.
- `docs/`: architecture, results and operational guides.

Keep changes focused. Run the unit suite before submitting a PR; changes to rewards or training also need the relevant parity or training checks. Update the tool declarations and registration tests together when adding or removing a tool.

Record measured results with their evaluation conditions. Label compute estimates and planned experiments so readers can tell them apart from completed runs.

Keep local configuration, training outputs and generated binaries outside the source tree.

See [Publishing](docs/PUBLISHING.md) for the GitHub repository and Hermes catalog PR workflow.
