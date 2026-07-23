# CLI reference

All commands accept `--config/-c`, defaulting to `circuitdk.toml`. Commands that support `--json`
write machine-readable results to stdout; logging and errors use stderr.

Use `circuitdk --version` to print the installed CircuitDK version.

## Commands

| Command | Purpose |
|---|---|
| `circuitdk synth` | Build the deterministic desired Circuit IR without opening KiCad |
| `circuitdk diff` | Show symbol, property, and no-connect operations; exits 2 when changes exist |
| `circuitdk deploy` | Atomically apply code-owned changes and report validation separately |
| `circuitdk test` | Check managed state, net partitions, pin coverage, libraries, and ERC |
| `circuitdk drift` | Compare managed KiCad fields with the last deployed snapshot |
| `circuitdk inspect` | Emit desired, actual, plan, drift, and library details |
| `circuitdk adopt` | Add `CircuitDK:ID` to an existing symbol selected by reference |
| `circuitdk move` | Rename a logical ID while preserving the KiCad symbol UUID |
| `circuitdk lock` | Write or verify resolved library source hashes |

## Exit codes

Exit codes are stable public behavior:

- `0`: the command completed successfully;
- `1`: configuration, parsing, library, KiCad CLI, or transaction failure;
- `2`: `diff` or `drift` found changes, or a strict conformance/electrical check failed.

`deploy` returning `0` means CircuitDK applied the managed state successfully. Manual wiring is an
expected follow-up after adding symbols, so `pin_not_connected` ERC results are reported as
`ACTION REQUIRED` without changing that exit code. `circuitdk test` remains strict and fails until
the declared connectivity is realized.

If deploy cannot reconcile the managed state, or ERC reports a non-wiring electrical error such as
a pin conflict, deploy exits `2`. Warnings do not change the default success exit code.

## Deploy status

Deploy reports separate outcomes so an applied file is never confused with a complete circuit:

- `APPLY SUCCEEDED` or `APPLY INCOMPLETE`: managed-state reconciliation;
- `SCHEMATIC VALID`: KiCad parsed the file and exported its netlist;
- `MANUAL WIRING REQUIRED`: declared connections are not yet drawn;
- `ELECTRICAL VALIDATION FAILED`: ERC found errors other than pending pin connections;
- `ERC WARNINGS`: non-fatal warnings to review.

The final colored line summarizes the action a user should take:

- `COMPLETE`: applied and electrically valid;
- `COMPLETE WITH WARNINGS`: valid with warnings to review;
- `ACTION REQUIRED`: applied successfully, but manual wiring remains;
- `INVALID`: applied successfully, but electrical violations remain;
- `FAILED`: managed state was not fully applied.

## JSON output

`circuitdk deploy --json` includes machine-readable status for each axis, including:

- `apply_status`, `complete`, and `reconciled`;
- `structural_validation` and `electrical_validation`;
- `manual_wiring_required` and `manual_wiring_issue_count`;
- `electrical_error_count`, `erc_error_count`, and `erc_warning_count`;
- `erc_violations` and `ready`.

JSON output contains no terminal colors or presentation-only status lines.
