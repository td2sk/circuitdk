from __future__ import annotations

from ..constructs import Construct, Net, Part, Pin
from ..parts import Capacitor, Resistor
from ..units import Quantity


def pull_down(
    *,
    signal: Pin,
    resistor: Resistor,
    ground: Net,
) -> None:
    signal.part.circuit.connect(signal, resistor.pin1)
    ground.connect(resistor.pin2)


def pull_up(
    *,
    signal: Pin,
    resistor: Resistor,
    power: Net,
) -> None:
    signal.part.circuit.connect(signal, resistor.pin1)
    power.connect(resistor.pin2)


def decouple(
    *,
    power_pin: Pin,
    capacitor: Capacitor,
    ground: Net,
) -> None:
    power_pin.part.circuit.connect(power_pin, capacitor.pin1)
    ground.connect(capacitor.pin2)


class LedIndicator(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        drive: Pin,
        return_to: Net,
        series_resistance: Quantity,
        led_footprint: str | None = None,
        resistor_footprint: str | None = None,
    ) -> None:
        super().__init__(scope, construct_id)
        self.resistor = Resistor(
            self,
            "Resistor",
            resistance=series_resistance,
            footprint=resistor_footprint,
        )
        self.led = Part(
            self,
            "Led",
            symbol="Device:LED",
            footprint=led_footprint,
            pins={"A": "1", "K": "2"},
        )
        self.circuit.connect(drive, self.resistor.pin1)
        self.circuit.connect(self.resistor.pin2, self.led.pin("A"))
        return_to.connect(self.led.pin("K"))


class VoltageDivider(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        input_net: Net,
        return_to: Net,
        upper_resistance: Quantity,
        lower_resistance: Quantity,
        footprint: str | None = None,
    ) -> None:
        super().__init__(scope, construct_id)
        self.upper = Resistor(self, "Upper", resistance=upper_resistance, footprint=footprint)
        self.lower = Resistor(self, "Lower", resistance=lower_resistance, footprint=footprint)
        self.output = Net(self, "Output")
        input_net.connect(self.upper.pin1)
        self.output.connect(self.upper.pin2, self.lower.pin1)
        return_to.connect(self.lower.pin2)


__all__ = [
    "LedIndicator",
    "VoltageDivider",
    "decouple",
    "pull_down",
    "pull_up",
]
