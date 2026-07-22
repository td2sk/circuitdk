from pathlib import Path

from circuitdk import Circuit, KicadProject, Part, V, kohm

SCHEMATIC = Path(__file__).parent / "hardware" / "blinky.kicad_sch"


def _ensure_example_schematic() -> None:
    if SCHEMATIC.exists():
        return
    # This example creates a minimal schematic if missing; real projects should use a KiCad file.
    # 回路図がなければサンプル用に作成します。実用時はKiCadの回路図を指定してください。
    SCHEMATIC.parent.mkdir(parents=True, exist_ok=True)
    SCHEMATIC.write_text(
        """(kicad_sch
  (version 20250114)
  (generator "circuitdk-example")
  (generator_version "0.1.0")
  (uuid 00000000-0000-4000-8000-000000000001)
  (paper "A4")
  (lib_symbols)
  (sheet_instances
    (path "/"
      (page "1")
    )
  )
)
""",
        encoding="utf-8",
        newline="",
    )


_ensure_example_schematic()

circuit = Circuit("Blinky")
vdd = circuit.power("VDD", voltage=5 * V)
gnd = circuit.ground("GND")

mcu = Part(
    circuit,
    "Mcu",
    symbol="MCU_Microchip_ATtiny:ATtiny85-20P",
    footprint="Package_DIP:DIP-8_W7.62mm",
    pin_overrides={"PB0": "5"},
)
resistor = Part(
    circuit,
    "LedResistor",
    symbol="Device:R",
    value=1 * kohm,
)
led = Part(
    circuit,
    "Led",
    symbol="Device:LED",
)

vdd.connect(mcu.pin("VCC"))
gnd.connect(mcu.pin("GND"), led.pin("K"))
circuit.connect(mcu.pin("PB0"), resistor.pin("1"))
circuit.connect(resistor.pin("2"), led.pin("A"))

for unused_pin in ("1", "2", "3", "6", "7"):
    mcu.pin(unused_pin).no_connect()

# Assembly-specific choices can instead be loaded from BOM or variant data.
resistor.footprint = "Resistor_SMD:R_0603_1608Metric"
led.footprint = "LED_SMD:LED_0603_1608Metric"

project = KicadProject(circuit, SCHEMATIC)
