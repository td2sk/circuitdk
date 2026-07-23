# Python API reference

[English](api-reference.md) | [日本語](api-reference.ja.md)

This is the compact reference for CircuitDK's alpha Python API. Import the types described here
from `circuitdk` unless another module is shown.

## Minimal structure

A user module builds one `Circuit`, creates parts and nets under it, and exports one
`KicadProject` for the CLI entrypoint:

```python
from circuitdk import Circuit, KicadProject, Part, V, kohm

circuit = Circuit("Blinky")
vdd = circuit.power("VDD", voltage=5 * V)
gnd = circuit.ground("GND")

power = Part(
    circuit,
    "PowerInput",
    symbol="Connector_Generic:Conn_01x02",
    pin_overrides={"VDD": "1", "GND": "2"},
)
resistor = Part(circuit, "LedResistor", symbol="Device:R", value=1 * kohm)
led = Part(circuit, "Led", symbol="Device:LED")

vdd.connect(power.pin("VDD"), resistor.pin("1"))
circuit.connect(resistor.pin("2"), led.pin("A"))
gnd.connect(led.pin("K"), power.pin("GND"))

project = KicadProject(circuit, "hardware/blinky.kicad_sch")
```

Point `circuitdk.toml` at the module-level `project` object:

```toml
[project]
entrypoint = "circuit:project"
state_directory = ".circuitdk"
```

The usual workflow is `circuitdk diff`, `circuitdk deploy`, manual arrangement and wiring in
KiCad, then `circuitdk test`.

## Identity and ownership

Every object receives a stable path from its scope and construct ID:

```python
circuit = Circuit("Board")
led = Part(circuit, "StatusLed", symbol="Device:LED")

assert led.path == "/Board/StatusLed"
```

Use these paths as CircuitDK IDs. Do not use mutable KiCad references such as `R1` as logical IDs.
Python owns managed part existence and fields; KiCad owns placement, rotation, wires, labels, and
presentation.

## Core types

### `Construct`

Base class for objects in the construct tree.

| Member | Meaning |
| --- | --- |
| `scope` | Parent construct, or `None` for the root circuit. |
| `construct_id` | ID unique within the parent scope. It cannot contain `/`. |
| `path` | Stable absolute logical ID derived from the construct tree. |
| `circuit` | Root `Circuit` containing the construct. |

Application-specific reusable circuits can subclass `Construct` and create child parts, nets, or
other constructs in `__init__`.

### `Circuit`

```python
Circuit(construct_id: str)
```

The root construct and mutable circuit builder.

| Method | Purpose |
| --- | --- |
| `net(id)` | Create a named signal `Net`. |
| `power(id, voltage=None)` | Create a named power `Net`. |
| `ground(id="GND")` | Create a ground `Net`. |
| `connect(*pins)` | Connect at least two pins through an anonymous net. |
| `no_connect(pin)` | Mark a pin as intentionally unused. Prefer `pin.no_connect()`. |
| `synth()` | Produce immutable `CircuitIR`. Normally the CLI calls this through `KicadProject`. |

Keep the returned `Part` and `Net` objects in normal Python variables; there is no public global
`Parts` collection in the alpha API.

### `Part`

```python
Part(
    scope,
    construct_id,
    *,
    symbol,
    pins=None,
    pin_overrides=None,
    value=None,
    footprint=None,
    in_bom=True,
    on_board=True,
    dnp=False,
)
```

| Argument or attribute | Meaning |
| --- | --- |
| `symbol` | KiCad library ID such as `Device:R`. Required. |
| `value` | Code-owned value. Defaults to the symbol name. A `Quantity` remains numeric until the KiCad serialization boundary; an explicit `str` is preserved unchanged. |
| `footprint` | KiCad footprint library ID, or `None`. May be assigned later from BOM data. |
| `in_bom` | Whether the symbol participates in the BOM. |
| `on_board` | Whether the symbol participates in PCB transfer. |
| `dnp` | Do-not-populate state. |
| `pin(name_or_number)` | Return a `Pin` by resolved name, alias, or number. |

By default, CircuitDK resolves all pins from the selected KiCad symbol library. Use
`pin_overrides` only for convenient aliases that differ from the library:

```python
mcu = Part(
    circuit,
    "Mcu",
    symbol="MCU_Microchip_ATtiny:ATtiny85-20P",
    pin_overrides={"PB0": "5"},  # KiCad calls this pin AREF/PB0.
)
```

Use `pins={"name": "number"}` for generated or unavailable libraries. Supplying `pins` defines
the complete pin set and disables KiCad library pin resolution. `pins` and `pin_overrides` cannot
be used together.

### `Pin`

| Member | Meaning |
| --- | --- |
| `part` | Owning `Part`. |
| `name` | Resolved name or code-facing alias. |
| `number` | Physical symbol pin number. |
| `ref` | Immutable `PinRef` used by Circuit IR. |
| `no_connect()` | Mark the pin as intentionally unused and return the pin. |

Every resolved pin should be connected or explicitly marked no-connect before strict testing.

### `Net`

| Member | Meaning |
| --- | --- |
| `kind` | `signal`, `power`, or `ground`. |
| `voltage` | String-normalized voltage for power nets, otherwise `None`. |
| `connect(*pins)` | Add pins to the net and return the same `Net`. |

Calling `connect()` again extends the same logical net:

```python
vdd.connect(controller.pin("VCC"))
vdd.connect(sensor.pin("VDD"), capacitor.pin1)
```

## Passive parts

### `Resistor`, `Capacitor`, and `Inductor`

```python
Resistor(scope, id, *, resistance, footprint=None)
Capacitor(scope, id, *, capacitance, footprint=None)
Inductor(scope, id, *, inductance, footprint=None)
```

All three expose `pin1` and `pin2`. They retain their numeric value as `.resistance`,
`.capacitance`, or `.inductance` and use the corresponding `Device:R`, `Device:C`, or `Device:L`
symbol.

Import them from `circuitdk.parts`.

## Experimental circuit patterns

```python
from circuitdk.experimental.patterns import (
    LedIndicator,
    VoltageDivider,
    decouple,
    pull_down,
    pull_up,
)
```

These APIs are under active design and may change or be removed without deprecation, including in
patch releases. Pull and decoupling helpers accept explicitly created parts and add only ordinary
connectivity:

```python
pull_down(*, signal, resistor, ground)
pull_up(*, signal, resistor, power)
decouple(*, power_pin, capacitor, ground)
```

### `LedIndicator`

```python
LedIndicator(
    scope,
    id,
    *,
    drive,
    return_to,
    series_resistance,
    led_footprint=None,
    resistor_footprint=None,
)
```

Creates `.resistor` and `.led` and connects them in series.

### `VoltageDivider`

```python
VoltageDivider(
    scope,
    id,
    *,
    input_net,
    return_to,
    upper_resistance,
    lower_resistance,
    footprint=None,
)
```

Exposes `.upper`, `.lower`, and the divider output `.output` net.

## Protocol connections

SPI, I2C, and UART connections are available from `circuitdk.protocols`:

```python
from circuitdk.protocols import I2C, SPI, UART, pin_override
```

For each signal, select a pin by name or number relative to its controller or device, or pass a
`Pin` directly.

### `SPI`

```python
spi = SPI(
    scope,
    id,
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

Controller-side `mosi`/`sdo` and `miso`/`sdi` are aliases. Peripheral-side `sdi`/`mosi` and
`sdo`/`miso` are aliases. Specify at most one name from each pair. Data directions are optional,
but SPI requires at least one. `controller_cs` and `device_cs` must be supplied together or both
omitted.

### `I2C`

```python
i2c = I2C(scope, id, controller=controller, scl="SCL", sda="SDA")
i2c.add_peripheral(device=sensor, scl="SCL", sda="SDA")
```

Multiple peripherals share the declared SCL and SDA nets.

### `UART`

```python
UART(
    scope,
    id,
    left=controller,
    left_tx="TX",
    left_rx="RX",
    right=adapter,
    right_tx="TXD",
    right_rx="RXD",
)
```

UART connects left TX to right RX and left RX to right TX. Either direction may be omitted.

### Pin-name warnings

If a well-known pin name such as `SPI1_MOSI`, `SCLK`, `SDI`, `SDO`, `I2C_SDA`, `TXD`, or `RXD`
conflicts with its assigned role, CircuitDK reports a warning. General-purpose names such as
`GPIO2` remain valid. Use a reasoned override for intentional exceptions:

```python
sck=pin_override(
    sensor.pin("MISO"),
    reason="The shared legacy symbol has an incorrect pin name.",
)
```

## Values and units

Available units are `ohm`, `kohm`, `Mohm`, `F`, `uF`, `nF`, `H`, `mH`, `uH`, `nH`, and `V`:

```python
resistance = 10 * kohm
capacitance = 100 * nF
inductance = 2.2 * mH
supply = 3.3 * V
```

The result is an immutable, Decimal-based `Quantity`. It remains numeric in `Part` and `CircuitIR`,
supports equality by physical value, and can be converted for assertions:

```python
from decimal import Decimal

assert resistance.in_unit(ohm) == Decimal("10000")
assert resistance == 10000 * ohm
```

At the KiCad boundary, CircuitDK uses conventional compact passive notation. Examples include
`470R`, `4R7`, `3k3`, `100n`, `4u7`, and `2m2`. The unit selected in Python is retained, so
`0.3 * uF` becomes `0.3u`, while `300 * nF` becomes `300n`. Explicit string values are not
rewritten.

## `KicadProject`

```python
KicadProject(
    circuit,
    schematic,
    *,
    state_directory=".circuitdk",
    moved=None,
    validate_with_kicad=True,
)
```

`symbol_resolver`, `footprint_resolver`, and `kicad_cli` can also be injected for advanced use or
tests. Normal user code should rely on automatic discovery.

| Member | Purpose |
| --- | --- |
| `circuit` | Desired `Circuit`. |
| `schematic` | Target `.kicad_sch` as a `Path`. |
| `state_directory` | Directory for last-applied state and library lock data. |
| `moved` | Mapping of old logical IDs to new IDs. |
| `state_path` | Managed-state JSON path. |
| `lock_path` | Library lock JSON path. |
| `synth()` | Resolve libraries and return desired `CircuitIR`. |
| `plan()` | Compare desired state with the schematic. |
| `drift()` | Report managed KiCad-side changes since the previous deploy. |
| `deploy(backup=True)` | Apply managed changes atomically. |
| `run_tests()` | Run connectivity, pin, library, and ERC checks. |
| `inspect()` | Return desired, actual, plan, drift, and library data as a dictionary. |
| `library_lock()` | Resolve library hashes and report lock issues. |
| `adopt(reference, circuit_id)` | Attach a logical ID to an existing KiCad symbol. |
| `move(old_id, new_id)` | Rename a managed logical ID in the schematic. |

Prefer CLI commands for normal workflows because they provide stable output and exit-code
semantics. Direct methods are useful for tests and custom automation.

## Validation helpers

`validate_pin_coverage(circuit_ir)` checks that every resolved pin is connected or explicitly
no-connect. Its result exposes `.unspecified` and the boolean `.ok` property. Normal users can rely
on `circuitdk test`, which runs this check together with actual-schematic connectivity, library,
and ERC checks.

## Circuit IR

`CircuitIR`, `PartIR`, `NetIR`, and `PinRef` are immutable synthesized views. They are useful for
custom analysis and tests, but are not builders. Construct the design with `Circuit`, `Part`, and
`Net`, then call `project.synth()`.

The alpha API may still evolve. Public names re-exported from `circuitdk` are the supported user
surface; modules under `circuitdk.targets` are advanced backend APIs.
