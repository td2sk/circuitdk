from __future__ import annotations

from dataclasses import dataclass

from ..constructs import Construct, Part, Pin
from .common import PinRole, PinSelector, resolve_protocol_pin


@dataclass(frozen=True, slots=True)
class I2cPeripheral:
    id: str
    device: Part | None
    scl: Pin
    sda: Pin


class I2C(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        controller: Part | None = None,
        scl: PinSelector,
        sda: PinSelector,
    ) -> None:
        super().__init__(scope, construct_id)
        self.controller = controller
        self.scl = self._resolve(controller, scl, PinRole.I2C_CLOCK, "controller")
        self.sda = self._resolve(controller, sda, PinRole.I2C_DATA, "controller")
        self.peripherals: list[I2cPeripheral] = []
        self._peripheral_ids: set[str] = set()

    def add_peripheral(
        self,
        *,
        device: Part | None = None,
        id: str | None = None,
        scl: PinSelector,
        sda: PinSelector,
    ) -> I2cPeripheral:
        peripheral_id = id or (device.path if device is not None else None)
        if peripheral_id is None:
            raise ValueError("a peripheral without a device requires an explicit id")
        if peripheral_id in self._peripheral_ids:
            raise ValueError(f"duplicate I2C peripheral id {peripheral_id!r}")
        peripheral_scl = self._resolve(device, scl, PinRole.I2C_CLOCK, "peripheral")
        peripheral_sda = self._resolve(device, sda, PinRole.I2C_DATA, "peripheral")
        self.circuit.connect(self.scl, peripheral_scl)
        self.circuit.connect(self.sda, peripheral_sda)
        peripheral = I2cPeripheral(peripheral_id, device, peripheral_scl, peripheral_sda)
        self._peripheral_ids.add(peripheral_id)
        self.peripherals.append(peripheral)
        return peripheral

    def _resolve(
        self,
        owner: Part | None,
        selector: PinSelector,
        role: PinRole,
        endpoint: str,
    ) -> Pin:
        return resolve_protocol_pin(
            circuit=self.circuit,
            owner=owner,
            selector=selector,
            expected_role=role,
            endpoint=endpoint,
            protocol_path=self.path,
        )
