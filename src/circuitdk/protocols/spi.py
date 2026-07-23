from __future__ import annotations

from dataclasses import dataclass

from ..constructs import Construct, Part, Pin
from .common import PinRole, PinSelector, resolve_protocol_pin


@dataclass(frozen=True, slots=True)
class SpiPeripheral:
    id: str
    device: Part | None
    sck: Pin
    controller_to_peripheral: Pin | None
    peripheral_to_controller: Pin | None
    controller_cs: Pin | None
    device_cs: Pin | None


class SPI(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        controller: Part | None = None,
        sck: PinSelector,
        mosi: PinSelector | None = None,
        miso: PinSelector | None = None,
        sdo: PinSelector | None = None,
        sdi: PinSelector | None = None,
    ) -> None:
        super().__init__(scope, construct_id)
        self.controller = controller
        controller_out = _one_alias(mosi, sdo, "mosi", "sdo", required=False)
        controller_in = _one_alias(miso, sdi, "miso", "sdi", required=False)
        if controller_out is None and controller_in is None:
            raise ValueError("SPI requires at least one data direction")
        self.sck = self._resolve(controller, sck, PinRole.SPI_CLOCK, "controller")
        self.controller_to_peripheral = (
            self._resolve(
                controller,
                controller_out,
                PinRole.SPI_CONTROLLER_OUT,
                "controller",
            )
            if controller_out is not None
            else None
        )
        self.peripheral_to_controller = (
            self._resolve(
                controller,
                controller_in,
                PinRole.SPI_CONTROLLER_IN,
                "controller",
            )
            if controller_in is not None
            else None
        )
        self.peripherals: list[SpiPeripheral] = []
        self._peripheral_ids: set[str] = set()

    def add_peripheral(
        self,
        *,
        device: Part | None = None,
        id: str | None = None,
        sck: PinSelector,
        sdi: PinSelector | None = None,
        sdo: PinSelector | None = None,
        mosi: PinSelector | None = None,
        miso: PinSelector | None = None,
        controller_cs: PinSelector | None = None,
        device_cs: PinSelector | None = None,
    ) -> SpiPeripheral:
        peripheral_in = _one_alias(sdi, mosi, "sdi", "mosi", required=False)
        peripheral_out = _one_alias(sdo, miso, "sdo", "miso", required=False)
        if peripheral_in is not None and self.controller_to_peripheral is None:
            raise ValueError("peripheral input was specified, but the controller has no output")
        if peripheral_out is not None and self.peripheral_to_controller is None:
            raise ValueError("peripheral output was specified, but the controller has no input")
        if (controller_cs is None) != (device_cs is None):
            raise ValueError("controller_cs and device_cs must be specified together")

        peripheral_id = id or (device.path if device is not None else None)
        if peripheral_id is None:
            raise ValueError("a peripheral without a device requires an explicit id")
        if peripheral_id in self._peripheral_ids:
            raise ValueError(f"duplicate SPI peripheral id {peripheral_id!r}")

        peripheral_sck = self._resolve(device, sck, PinRole.SPI_CLOCK, "peripheral")
        input_pin = (
            self._resolve(
                device,
                peripheral_in,
                PinRole.SPI_CONTROLLER_OUT,
                "peripheral",
            )
            if peripheral_in is not None
            else None
        )
        output_pin = (
            self._resolve(
                device,
                peripheral_out,
                PinRole.SPI_CONTROLLER_IN,
                "peripheral",
            )
            if peripheral_out is not None
            else None
        )
        controller_select = (
            self._resolve(
                self.controller,
                controller_cs,
                PinRole.SPI_CHIP_SELECT,
                "controller",
            )
            if controller_cs is not None
            else None
        )
        device_select = (
            self._resolve(
                device,
                device_cs,
                PinRole.SPI_CHIP_SELECT,
                "peripheral",
            )
            if device_cs is not None
            else None
        )

        self.circuit.connect(self.sck, peripheral_sck)
        if self.controller_to_peripheral is not None and input_pin is not None:
            self.circuit.connect(self.controller_to_peripheral, input_pin)
        if self.peripheral_to_controller is not None and output_pin is not None:
            self.circuit.connect(self.peripheral_to_controller, output_pin)
        if controller_select is not None and device_select is not None:
            self.circuit.connect(controller_select, device_select)

        peripheral = SpiPeripheral(
            peripheral_id,
            device,
            peripheral_sck,
            input_pin,
            output_pin,
            controller_select,
            device_select,
        )
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


def _one_alias(
    first: PinSelector | None,
    second: PinSelector | None,
    first_name: str,
    second_name: str,
    *,
    required: bool,
) -> PinSelector | None:
    if first is not None and second is not None:
        raise ValueError(f"{first_name} and {second_name} are aliases; specify only one")
    result = first if first is not None else second
    if required and result is None:
        raise ValueError(f"one of {first_name} or {second_name} is required")
    return result
