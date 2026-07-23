# Getting started

This guide explains the complete CircuitDK workflow after the introductory example in the
[README](../README.md#quick-start).

## Install

Install CircuitDK from PyPI as a uv tool:

```console
uv tool install circuitdk
circuitdk --version
```

To install from a source checkout instead, change to its root and install the CLI package directly:

```console
cd circuitdk
uv tool install .
circuitdk --version
```

This is a non-editable installation. After pulling a newer version, reinstall it:

```console
uv tool install --reinstall .
```

Development environment setup belongs in the [development guide](development.md).

## Create a project

A minimal user project contains the Python circuit definition, CircuitDK configuration, and an
existing KiCad 10 schematic:

```text
my-board/
|-- circuit.py
|-- circuitdk.toml
`-- hardware/
    `-- board.kicad_sch
```

Create and save the empty schematic with KiCad before the first diff or deploy. CircuitDK updates a
schematic; it does not create an entire KiCad project from nothing.

Define a module-level `KicadProject` object in `circuit.py`. The README contains a complete
MCU-free [connector, resistor, and LED example](../README.md#quick-start) that avoids unrelated
unused-pin ERC errors.

Point `circuitdk.toml` at that object:

```toml
[project]
entrypoint = "circuit:project"
state_directory = ".circuitdk"
```

The entrypoint has the form `module:object`. CircuitDK imports the module from the configuration
directory and loads the named `KicadProject`.

## Preview the desired circuit

Synthesize the Python model without changing KiCad files:

```console
circuitdk synth
```

Then compare code-owned state with the schematic:

```console
circuitdk diff
```

Diff uses stable logical paths such as `/Blinky/LedResistor`, not KiCad references such as `R1`.
Additions are green, updates are yellow, and removals are red. Exit code `2` means differences were
found; it does not mean diff itself failed.

## Deploy managed state

Apply the plan:

```console
circuitdk deploy
```

Deploy inserts new symbols and their embedded library definitions into a staging area. It updates
only code-owned fields on existing managed symbols. Existing positions, rotations, fields, wires,
labels, junctions, and graphics are preserved.

The write is transactional: CircuitDK writes and reparses a temporary file, asks KiCad to parse it
and export a netlist, verifies that the source did not change concurrently, and then replaces the
schematic atomically. Save and close the schematic in KiCad before deploying.

## Complete manual wiring

CircuitDK declares intended connectivity but deliberately does not route wires. After adding parts:

1. open the deployed schematic in KiCad;
2. move symbols out of the staging area;
3. draw wires or place the appropriate KiCad connectivity labels and power symbols;
4. save and close the schematic.

An otherwise successful deploy can report `ACTION REQUIRED` and `pin_not_connected`. This means
the managed state was applied and manual wiring remains. That condition does not make deploy fail.

Run the strict conformance checks after wiring:

```console
circuitdk test
```

Test exports the actual XML netlist with KiCad 10, compares logical pin partitions, checks pin
coverage, validates resolved libraries and footprints, and runs ERC. Unlike deploy, test remains
unsuccessful until declared connections are realized.

## Symbol and footprint libraries

Generic `Part` resolves pin names from project and global `sym-lib-table` files automatically.
CircuitDK understands nested table entries and `${KIPRJMOD}` / `${KICAD10_SYMBOL_DIR}` variables.
Use `pin_overrides={"alias": "number"}` when a convenient code-facing name differs from the
library name; all other pins are still resolved from KiCad. An explicit
`pins={"name": "number"}` map remains available for generated or unavailable libraries and
disables library pin resolution for that part.

Footprints that are intrinsic to a selected component can be specified in its constructor.
Assembly-specific footprints can be assigned later or loaded from BOM/variant data. See
[Managing footprints](../README.md#managing-footprints) for both approaches and a CSV example.

Set `CIRCUITDK_KICAD_CLI` when `kicad-cli` is outside `PATH`. On Windows, CircuitDK automatically
detects the standard path:

```text
C:\Program Files\KiCad\10.0\bin\kicad-cli.exe
```

## Explicit unused pins

Every resolved pin should either be connected or explicitly marked as intentionally unused:

```python
part.pin("UNUSED_PIN_NAME").no_connect()
```

Use the exact pin name or number from the selected KiCad symbol. Deploy creates or removes the
corresponding KiCad no-connect marker, and test reports pins left unspecified.

## Existing schematics

Bring an existing unmanaged symbol under CircuitDK control by reference:

```console
circuitdk adopt --reference R1 --id /Board/StatusLed/Resistor
```

CircuitDK adds a hidden `CircuitDK:ID` property without replacing or moving the symbol.

Declare a logical ID refactor in Python to preserve the KiCad UUID and presentation:

```python
project = KicadProject(
    circuit,
    "hardware/board.kicad_sch",
    moved={"/Board/OldName": "/Board/NewName"},
)
```

The direct migration command is also available:

```console
circuitdk move --from /Board/OldName --to /Board/NewName
```

Use `circuitdk drift` to report code-owned fields that have changed in KiCad since the previous
deploy. Desired Python state wins on the next deploy.

## High-level circuit APIs

Pull resistors, decoupling helpers, LED indicators, and voltage dividers currently live under
`circuitdk.experimental.patterns`. They create ordinary parts and connectivity without hidden
semantic validation. Experimental APIs may change or be removed without deprecation, including in
patch releases.

See [High-level circuit APIs](../README.md#high-level-circuit-apis) for examples.

## Protocol-aware connections

`SPI`, `I2C`, and `UART` keep pin selection explicit while checking well-known pin names for clear
role conflicts:

```python
from circuitdk.protocols import SPI

spi = SPI(
    circuit,
    "SensorBus",
    controller=controller,
    sck="SPI_SCK",
    mosi="SPI_MOSI",
    miso="SPI_MISO",
)
spi.add_peripheral(
    device=sensor,
    sck="SCLK",
    sdi="SDI",
    sdo="SDO",
    controller_cs="SENSOR_CS",
    device_cs="NCS",
)
```

Names such as `GPIO2` that do not carry reliable protocol meaning are accepted without a warning.
See the [API reference](api-reference.md#protocol-connections) for aliases, one-way links, and
reasoned overrides.
