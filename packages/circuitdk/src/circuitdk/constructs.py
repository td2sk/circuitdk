from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from .ir import CircuitIR, IntentIR, NetIR, PartIR, PinRef
from .units import Quantity


class Construct:
    def __init__(self, scope: Construct | None, construct_id: str) -> None:
        if not construct_id or "/" in construct_id:
            raise ValueError("construct id must be non-empty and must not contain '/'")
        self.scope = scope
        self.construct_id = construct_id
        self._children: dict[str, Construct] = {}
        if scope is not None:
            if construct_id in scope._children:
                raise ValueError(f"duplicate construct id {construct_id!r} under {scope.path}")
            scope._children[construct_id] = self

    @property
    def path(self) -> str:
        if self.scope is None:
            return f"/{self.construct_id}"
        return f"{self.scope.path}/{self.construct_id}"

    @property
    def circuit(self) -> Circuit:
        current: Construct = self
        while current.scope is not None:
            current = current.scope
        if not isinstance(current, Circuit):
            raise RuntimeError("construct is not attached to a Circuit")
        return current


@dataclass(frozen=True, slots=True)
class Pin:
    part: Part
    name: str
    number: str

    @property
    def ref(self) -> PinRef:
        return PinRef(self.part.path, self.number, self.name)

    def no_connect(self) -> Pin:
        self.part.circuit.no_connect(self)
        return self


class Part(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        symbol: str,
        pins: Mapping[str, str] | None = None,
        pin_overrides: Mapping[str, str] | None = None,
        value: str | Quantity | None = None,
        footprint: str | None = None,
        in_bom: bool = True,
        on_board: bool = True,
        dnp: bool = False,
    ) -> None:
        super().__init__(scope, construct_id)
        if ":" not in symbol:
            raise ValueError("symbol must be a KiCad library identifier such as 'Device:R'")
        if pins is not None and pin_overrides is not None:
            raise ValueError("pins and pin_overrides cannot be used together")
        self.symbol = symbol
        self.value = str(value) if value is not None else symbol.rsplit(":", 1)[-1]
        self.footprint = footprint
        self.in_bom = in_bom
        self.on_board = on_board
        self.dnp = dnp
        self._resolve_pins = pins is None
        initial_pins = pins if pins is not None else pin_overrides or {}
        self._pins = {name: Pin(self, name, number) for name, number in initial_pins.items()}
        numbers = [pin.number for pin in self._pins.values()]
        if len(numbers) != len(set(numbers)):
            raise ValueError(f"duplicate pin number on {self.path}")
        self.circuit._parts.append(self)

    def pin(self, name_or_number: str) -> Pin:
        if self._resolve_pins and name_or_number not in self._pins:
            self._pins[name_or_number] = Pin(self, name_or_number, name_or_number)
        if name_or_number in self._pins:
            return self._pins[name_or_number]
        matches = [pin for pin in self._pins.values() if pin.number == name_or_number]
        if len(matches) != 1:
            raise KeyError(f"pin {name_or_number!r} does not exist or is ambiguous on {self.path}")
        return matches[0]


class Net(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        kind: str = "signal",
        voltage: Quantity | None = None,
    ) -> None:
        super().__init__(scope, construct_id)
        self.kind = kind
        self.voltage = str(voltage) if voltage is not None else None
        self._pins: list[Pin] = []
        self.circuit._nets.append(self)

    def connect(self, *pins: Pin) -> Net:
        for pin in pins:
            if pin.part.circuit is not self.circuit:
                raise ValueError("cannot connect pins from another circuit")
            if pin not in self._pins:
                self._pins.append(pin)
        return self


class Circuit(Construct):
    def __init__(self, construct_id: str) -> None:
        self._parts: list[Part] = []
        self._nets: list[Net] = []
        self._anonymous_connections: list[tuple[Pin, ...]] = []
        self._intents: list[IntentIR] = []
        self._no_connects: set[Pin] = set()
        super().__init__(None, construct_id)

    def net(self, construct_id: str) -> Net:
        return Net(self, construct_id)

    def ground(self, construct_id: str = "GND") -> Net:
        return Net(self, construct_id, kind="ground", voltage=None)

    def power(self, construct_id: str, *, voltage: Quantity | None = None) -> Net:
        return Net(self, construct_id, kind="power", voltage=voltage)

    def connect(self, *pins: Pin) -> None:
        if len(pins) < 2:
            raise ValueError("a connection requires at least two pins")
        if any(pin.part.circuit is not self for pin in pins):
            raise ValueError("cannot connect pins from another circuit")
        self._anonymous_connections.append(tuple(pins))

    def add_intent(self, kind: str, subject: str, **parameters: object) -> None:
        normalized = tuple(sorted((name, str(value)) for name, value in parameters.items()))
        self._intents.append(IntentIR(kind, subject, normalized))

    def no_connect(self, pin: Pin) -> None:
        if pin.part.circuit is not self:
            raise ValueError("cannot mark a pin from another circuit as no-connect")
        self._no_connects.add(pin)

    def synth(self) -> CircuitIR:
        part_irs = tuple(
            PartIR(
                id=part.path,
                symbol=part.symbol,
                value=part.value,
                footprint=part.footprint,
                pins=tuple(
                    sorted((pin.ref for pin in part._pins.values()), key=lambda p: p.number)
                ),
                in_bom=part.in_bom,
                on_board=part.on_board,
                dnp=part.dnp,
                resolve_pins=part._resolve_pins,
            )
            for part in sorted(self._parts, key=lambda item: item.path)
        )

        groups: list[tuple[str | None, str, str | None, set[PinRef]]] = []
        for net in self._nets:
            groups.append((net.path, net.kind, net.voltage, {pin.ref for pin in net._pins}))
        for connection in self._anonymous_connections:
            groups.append((None, "signal", None, {pin.ref for pin in connection}))

        merged = _merge_overlapping(groups)
        connected = {pin for _, _, _, pins in merged for pin in pins}
        conflicting = sorted(pin.ref.key for pin in self._no_connects if pin.ref in connected)
        if conflicting:
            raise ValueError(f"pins are both connected and no-connect: {conflicting}")
        net_irs: list[NetIR] = []
        for name, kind, voltage, pins in merged:
            if not pins:
                continue
            stable_name = name or _anonymous_net_name(pins)
            net_irs.append(NetIR(stable_name, tuple(sorted(pins)), kind, voltage))
        return CircuitIR(
            self.path,
            part_irs,
            tuple(sorted(net_irs, key=lambda item: item.id)),
            tuple(sorted(self._intents, key=lambda item: (item.kind, item.subject))),
            tuple(sorted(pin.ref for pin in self._no_connects)),
        )


def _merge_overlapping(
    groups: Iterable[tuple[str | None, str, str | None, set[PinRef]]],
) -> list[tuple[str | None, str, str | None, set[PinRef]]]:
    result: list[tuple[str | None, str, str | None, set[PinRef]]] = []
    for name, kind, voltage, pins in groups:
        overlap = [index for index, item in enumerate(result) if item[3] & pins]
        if not overlap:
            result.append((name, kind, voltage, set(pins)))
            continue
        merged_names = [name]
        merged_pins = set(pins)
        chosen_kind, chosen_voltage = kind, voltage
        for index in reversed(overlap):
            old_name, old_kind, old_voltage, old_pins = result.pop(index)
            merged_names.append(old_name)
            merged_pins.update(old_pins)
            if old_name is not None:
                chosen_kind, chosen_voltage = old_kind, old_voltage
        concrete_names = {item for item in merged_names if item is not None}
        if len(concrete_names) > 1:
            raise ValueError(f"named nets are shorted in desired circuit: {sorted(concrete_names)}")
        result.append((next(iter(concrete_names), None), chosen_kind, chosen_voltage, merged_pins))
    return result


def _anonymous_net_name(pins: set[PinRef]) -> str:
    keys = "--".join(pin.key.lstrip("/").replace("/", "_") for pin in sorted(pins))
    return f"/__anonymous__/{keys}"
