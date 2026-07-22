# Initial release implementation record

This file is internal project memory. It records the completion contract used for the first usable
release and implementation details that should not be presented as user documentation.

## Completion contract

| Requirement | Implementation | Verification |
|---|---|---|
| Lossless S-expression updates | `circuitdk-lossless-sexpr` CST and non-overlapping text edits | parser round-trip and minimal-edit tests |
| Stable logical identity | Construct paths and hidden `CircuitDK:ID` | adopt, move, moved-declaration, drift tests |
| KiCad library discovery | project/global/nested tables and path-variable expansion | local-table tests plus standard `Device:R` system test |
| Symbol creation | embedded definitions, pin UUIDs, reference allocation, staging grid | real KiCad 10 netlist export after deploy |
| Code-owned updates/deletes | field patches, symbol-type pin rebuild, safe symbol deletion | backend integration tests |
| KiCad-owned presentation | position, rotation, fields, wires, labels and graphics preserved | byte-minimal patch tests |
| Connectivity conformance | KiCad XML netlist converted to logical pin partitions | missing/extra and hierarchical-property mapping tests |
| Explicit no-connect | DSL intent and transformed KiCad marker reconciliation | unit test and zero-ERC real KiCad system test |
| High-level intent | pull-up/down, decoupling, LED, divider, interfaces | topology intent-rule tests |
| KiCad ERC | structured JSON diagnostics during deploy and test | parser test and real KiCad 10 system test |
| Library reproducibility | source paths and SHA-256 lock entries | lock round-trip/difference and CLI smoke tests |
| Transaction safety | reparse, KiCad validation, source hash check, backup, atomic replace | deploy integration tests |

## Completed implementation notes

- uv workspace with `circuitdk-lossless-sexpr` and `circuitdk` packages
- byte-preserving S-expression CST and typed KiCad symbol/property views
- construct paths, generic parts, pins, nets, power/ground, values, immutable IR
- semantic connectivity partition comparison
- managed property diff, drift classification, and atomic deploy
- versioned JSON state, Typer CLI, JSON output, Ruff, ty, and pytest gates
- lazy project/global library resolution with one parse per referenced file per command
- standalone embedded definitions for inherited KiCad library symbols
- no-connect reconciliation, high-level constructs, footprint validation, and library locking

## Internal follow-up

- Red/Green tree implementation with persistent immutable green nodes and typed red views
- property-based parser testing

## Release gates

```console
uv run ruff format --check .
uv run ruff check .
uv run ty check
uv run pytest
```
