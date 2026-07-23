from __future__ import annotations

from .constructs import Construct, Net, Part, Pin
from .units import Quantity


class Resistor(Part):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        resistance: Quantity,
        footprint: str | None = None,
    ) -> None:
        self.resistance = resistance
        super().__init__(
            scope,
            construct_id,
            symbol="Device:R",
            value=resistance,
            footprint=footprint,
            pins={"1": "1", "2": "2"},
        )

    @property
    def pin1(self) -> Pin:
        return self.pin("1")

    @property
    def pin2(self) -> Pin:
        return self.pin("2")


class Capacitor(Part):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        capacitance: Quantity,
        footprint: str | None = None,
    ) -> None:
        self.capacitance = capacitance
        super().__init__(
            scope,
            construct_id,
            symbol="Device:C",
            value=capacitance,
            footprint=footprint,
            pins={"1": "1", "2": "2"},
        )

    @property
    def pin1(self) -> Pin:
        return self.pin("1")

    @property
    def pin2(self) -> Pin:
        return self.pin("2")


class Inductor(Part):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        inductance: Quantity,
        footprint: str | None = None,
    ) -> None:
        self.inductance = inductance
        super().__init__(
            scope,
            construct_id,
            symbol="Device:L",
            value=inductance,
            footprint=footprint,
            pins={"1": "1", "2": "2"},
        )

    @property
    def pin1(self) -> Pin:
        return self.pin("1")

    @property
    def pin2(self) -> Pin:
        return self.pin("2")


def pull_down(
    scope: Construct,
    construct_id: str,
    *,
    signal: Pin,
    ground: Net,
    resistance: Quantity,
    footprint: str | None = None,
) -> Resistor:
    resistor = Resistor(
        scope,
        construct_id,
        resistance=resistance,
        footprint=footprint,
    )
    scope.circuit.connect(signal, resistor.pin1)
    ground.connect(resistor.pin2)
    scope.circuit.add_intent(
        "default_logic_level",
        signal.ref.key,
        level="low",
        resistance=resistance,
        resistor=resistor.path,
    )
    return resistor


def pull_up(
    scope: Construct,
    construct_id: str,
    *,
    signal: Pin,
    power: Net,
    resistance: Quantity,
    footprint: str | None = None,
) -> Resistor:
    resistor = Resistor(
        scope,
        construct_id,
        resistance=resistance,
        footprint=footprint,
    )
    scope.circuit.connect(signal, resistor.pin1)
    power.connect(resistor.pin2)
    scope.circuit.add_intent(
        "default_logic_level",
        signal.ref.key,
        level="high",
        resistance=resistance,
        resistor=resistor.path,
    )
    return resistor


class DecouplingCapacitor(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        power_pin: Pin,
        ground: Net,
        capacitance: Quantity,
        footprint: str | None = None,
    ) -> None:
        super().__init__(scope, construct_id)
        self.capacitor = Capacitor(
            self,
            "Capacitor",
            capacitance=capacitance,
            footprint=footprint,
        )
        self.circuit.connect(power_pin, self.capacitor.pin1)
        ground.connect(self.capacitor.pin2)
        self.circuit.add_intent(
            "decoupling",
            power_pin.ref.key,
            capacitance=capacitance,
            capacitor=self.capacitor.path,
            ground=ground.path,
        )


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
        self.circuit.add_intent(
            "current_limited_led",
            self.led.path,
            drive=drive.ref.key,
            resistance=series_resistance,
            resistor=self.resistor.path,
        )


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
        self.circuit.add_intent(
            "voltage_divider",
            self.output.path,
            input=input_net.path,
            return_to=return_to.path,
            upper=self.upper.path,
            lower=self.lower.path,
            upper_resistance=upper_resistance,
            lower_resistance=lower_resistance,
        )
