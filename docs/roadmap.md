# Roadmap

This page describes user-visible areas CircuitDK may support in the future. It is directional and
does not promise a release date or implementation order.

## Current scope

CircuitDK currently targets KiCad 10 and a single root schematic. It reconciles parts, managed
properties, and no-connect markers while leaving symbol placement and wire routing to KiCad. The
CLI provides semantic diff, deploy, drift detection, connectivity checks, intent rules, ERC, and
library locking.

CircuitDK can consume connectivity exported by an existing KiCad design, including labels,
junctions, power symbols, and hierarchical references. Creating or managing hierarchical sheets
is not part of the current release.

See the [README](../README.md#current-scope) for practical limitations.

## Authoring and reuse

- a broader user-friendly high-level circuit authoring API
- richer high-level test assertions
- typed part libraries and generated Python bindings
- reusable part metadata for interfaces, electrical constraints, and valid default footprints
- a multi-circuit workspace for projects such as split boards

## KiCad integration

- hierarchical-sheet management
- design block integration
- optional label-stub connectivity realization
- a KiCad 11 IPC or hybrid backend behind the same user-facing model

## Performance and tooling

- persistent semantic library caches across CLI invocations
- a standalone schematic inspector built on the lossless syntax layer
