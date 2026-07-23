from __future__ import annotations

from .constructs import Construct, Part, Pin
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
