# CircuitDK

CircuitDK brings infrastructure-as-code-style workflows to KiCad 10 schematics. Define parts,
properties, intended connectivity, and reusable circuit intent in Python while keeping placement,
wiring, labels, and presentation editable in KiCad.

## Install

Install the command from PyPI with [uv](https://docs.astral.sh/uv/):

```console
uv tool install circuitdk
circuitdk --version
```

CircuitDK requires Python 3.13 or later and `kicad-cli` from KiCad 10. Set
`CIRCUITDK_KICAD_CLI` if the executable is not in a standard location.

## Minimal example

Create and save an empty KiCad 10 schematic at `hardware/blinky.kicad_sch`, then define an LED
circuit in `circuit.py`:

```python
from circuitdk import Circuit, KicadProject, Part, V, kohm

circuit = Circuit("Blinky")
vdd = circuit.power("VDD", voltage=5 * V)
gnd = circuit.ground("GND")

power = Part(
    circuit,
    "PowerInput",
    symbol="Connector_Generic:Conn_01x02",
    footprint="Connector_PinHeader_2.54mm:PinHeader_1x02_P2.54mm_Vertical",
    pin_overrides={"VDD": "1", "GND": "2"},
)
resistor = Part(circuit, "LedResistor", symbol="Device:R", value=1 * kohm)
led = Part(circuit, "Led", symbol="Device:LED")

vdd.connect(power.pin("VDD"), resistor.pin("1"))
circuit.connect(resistor.pin("2"), led.pin("A"))
gnd.connect(led.pin("K"), power.pin("GND"))

resistor.footprint = "Resistor_SMD:R_0603_1608Metric"
led.footprint = "LED_SMD:LED_0603_1608Metric"

project = KicadProject(circuit, "hardware/blinky.kicad_sch")
```

Point `circuitdk.toml` at the module-level project:

```toml
[project]
entrypoint = "circuit:project"
state_directory = ".circuitdk"
```

Preview and deploy the managed changes, arrange and wire the symbols in KiCad, then verify the
result:

```console
circuitdk diff
circuitdk deploy
circuitdk test
```

Deploy preserves KiCad-owned placement and wire geometry. Missing manual wiring is reported
separately from apply failures, so it is clear whether the file update succeeded.

## Documentation

- [Project overview and full quick start](https://github.com/td2sk/circuitdk/blob/main/README.md)
- [Getting started](https://github.com/td2sk/circuitdk/blob/main/docs/getting-started.md)
- [Python API reference](https://github.com/td2sk/circuitdk/blob/main/docs/api-reference.md)
- [CLI reference](https://github.com/td2sk/circuitdk/blob/main/docs/cli.md)
- [Japanese README](https://github.com/td2sk/circuitdk/blob/main/README.ja.md)

## Alpha status

CircuitDK is an alpha release. It targets KiCad 10, manages flat schematics, and leaves wire
routing to a person or external layout automation. Review diffs and keep the schematic under
version control. CircuitDK validates declared structure and KiCad ERC results, but it does not
prove electrical correctness or manufacturing suitability.
