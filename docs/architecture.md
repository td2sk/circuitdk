# Architecture

## Purpose

CircuitDK treats Python as the authoritative source for circuit logic while preserving KiCad as
the editor for schematic presentation. It is a reconciler, not a schematic renderer.

```text
Python constructs -> Desired Circuit IR -> Deployment planner
                                             ^          |
                                             |          v
KiCad netlist -> Actual Circuit IR       typed view -> minimal CST patch
```

## Ownership

Code owns managed symbol existence, library ID, value, footprint, BOM flags, stable logical ID,
and intended connectivity. KiCad owns coordinates, rotation, field positions, wires, junctions,
labels, and graphics. Connectivity is compared as partitions of logical pins; wire geometry is
never part of the desired IR.

The KiCad 10 backend resolves project and global library tables, embeds required library symbol
definitions, and inserts missing instances in a 50 mil aligned staging area. Existing managed
symbols are matched by their hidden `CircuitDK:ID` property. Removing a construct removes its
symbol but deliberately preserves KiCad-owned wires, which can then be cleaned up in KiCad.

`kicad-cli` exports the actual XML netlist. Because KiCad performs this export, direct wires,
labels, hierarchical references, junctions, and power symbols all use KiCad's own connectivity
semantics. CircuitDK can consume and validate that existing connectivity, but it does not currently
create or manage hierarchical sheets. CircuitDK converts references back to logical IDs and
compares partitions of logical pins. ERC is run during both deploy validation and
`circuitdk test`.

## Packages

`circuitdk-lossless-sexpr` contains no KiCad or circuit knowledge. It provides tokens, source spans, a
lossless CST, diagnostics, queries, and non-overlapping text edits. Unchanged input renders byte
for byte identically.

`circuitdk` contains constructs, immutable IR, intent rules, library and footprint resolution,
connectivity conformance, project/state/lock handling, the KiCad typed syntax facade,
reconciliation, and CLI.

## Library loading

Project declaration is side-effect free: constructing `KicadProject` does not inspect KiCad
tables, symbol or footprint files, or discover `kicad-cli`. These services are initialized lazily
only when the selected command needs them. In particular, `synth` with explicit pin maps, and an
unchanged `diff` whose parts all have explicit pin maps, do not load KiCad libraries. Parts that
need pin-name resolution still load their referenced symbol libraries during synthesis.

Within one command, the symbol resolver caches both resolved library IDs and parsed library
files. Multiple IDs such as `Device:R`, `Device:C`, and `Device:LED` therefore share one parse of
`Device.kicad_sym`. This is an in-process cache; persistent cross-command caching is not currently
implemented.

KiCad library symbols that use `extends` are kept as an inheritance chain for semantic pin and
property resolution, but are materialized differently for a schematic. CircuitDK copies the root
graphics and pins, overlays properties from root to leaf, renames nested units to the leaf symbol,
removes `extends`, and embeds only the standalone leaf definition. This matches KiCad 10's own
`lib_symbols` cache representation. Deploy also recognizes and repairs the older CircuitDK form
that embedded both the base and inherited leaf definitions.

## State and drift

There is no three-way merge. Desired state always wins for code-owned fields. The previous
applied snapshot is retained only to classify drift:

- desired vs actual: deployment plan;
- applied vs actual: KiCad-side managed drift;
- applied vs desired: source-code changes.

State files are versioned JSON and are written only after a successful schematic transaction.
The library lock independently records the source path and SHA-256 of every resolved symbol and
footprint library entry.

## Safety invariants

- Unmodified S-expressions round-trip exactly.
- A patch may touch only the selected token spans.
- Overlapping edits are rejected.
- Deploy writes a temporary file, reparses it, validates its structure with KiCad netlist export,
  checks the source hash, then atomically replaces it. Structural failure aborts the transaction.
- ERC runs after the valid schematic transaction. Manual-wiring diagnostics and electrical errors
  are reported without rolling back managed changes that were already applied.
- Unknown nodes and properties are preserved.
- Wires are never deleted or rewritten.
- The desired IR is deterministic for identical user code.
