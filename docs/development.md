# Development

This guide is for contributors working from a source checkout. End users should follow the
[source installation](../README.md#installation-from-source) instructions instead.

Install the workspace dependencies:

```console
uv sync
```

An optional editable CLI installation keeps the global command connected to the checkout:

```console
uv tool install --editable ./packages/circuitdk
```

Run all local gates from the repository root:

```console
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```

Tests are split between the reusable parser package and CircuitDK integration tests. Fixtures
should be actual KiCad 10 output where possible. Never normalize a fixture before round-trip
testing: exact whitespace, ordering, and unknown syntax are part of the contract.

The full suite auto-discovers KiCad 10 when it is available. Run the real deploy, netlist, and ERC
system tests explicitly before changing the KiCad backend or preparing a release:

```powershell
$env:CIRCUITDK_KICAD_CLI = "C:\Program Files\KiCad\10.0\bin\kicad-cli.exe"
uv run pytest -m kicad -v
```
