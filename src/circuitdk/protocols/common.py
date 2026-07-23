from __future__ import annotations

import warnings
from dataclasses import dataclass
from enum import Enum
from typing import TypeAlias

from ..constructs import Circuit, Part, Pin


class ProtocolPinWarning(UserWarning):
    """A declared protocol role conflicts with evidence in a pin name."""


class PinRole(Enum):
    SPI_CLOCK = "SPI clock"
    SPI_CONTROLLER_OUT = "SPI controller-to-peripheral data"
    SPI_CONTROLLER_IN = "SPI peripheral-to-controller data"
    SPI_CHIP_SELECT = "SPI chip select"
    I2C_CLOCK = "I2C clock"
    I2C_DATA = "I2C data"
    UART_TX = "UART transmit"
    UART_RX = "UART receive"


RawPinSelector: TypeAlias = Pin | str | int


@dataclass(frozen=True, slots=True)
class PinOverride:
    selector: RawPinSelector
    reason: str

    def __post_init__(self) -> None:
        if not self.reason.strip():
            raise ValueError("a pin override requires a non-empty reason")


PinSelector: TypeAlias = RawPinSelector | PinOverride


def pin_override(selector: RawPinSelector, *, reason: str) -> PinOverride:
    """Allow an intentional protocol-role or owner mismatch with a reason."""

    return PinOverride(selector, reason)


def resolve_protocol_pin(
    *,
    circuit: Circuit,
    owner: Part | None,
    selector: PinSelector,
    expected_role: PinRole,
    endpoint: str,
    protocol_path: str,
) -> Pin:
    overridden = isinstance(selector, PinOverride)
    raw = selector.selector if overridden else selector
    if isinstance(raw, bool):
        raise TypeError("a boolean is not a valid pin number")
    if isinstance(raw, Pin):
        pin = raw
    elif isinstance(raw, (str, int)):
        if owner is None:
            raise ValueError(
                f"{protocol_path} uses relative pin {raw!r} for {endpoint}, "
                "but no owner part was specified"
            )
        pin = owner.pin(str(raw))
    else:
        raise TypeError(f"unsupported pin selector: {raw!r}")

    if pin.part.circuit is not circuit:
        raise ValueError(f"{pin.ref.key} belongs to another circuit")

    if not overridden and owner is not None and pin.part is not owner:
        _warn(
            protocol_path,
            pin,
            endpoint,
            f"belongs to {pin.part.path}, but the declared endpoint owner is {owner.path}",
        )

    if not overridden:
        inferred = infer_pin_roles(pin.name, endpoint=endpoint)
        if len(inferred) == 1 and expected_role not in inferred:
            inferred_role = next(iter(inferred))
            _warn(
                protocol_path,
                pin,
                endpoint,
                f"is assigned as {expected_role.value}, but its name suggests "
                f"{inferred_role.value}",
            )
    return pin


def _warn(
    protocol_path: str,
    pin: Pin,
    endpoint: str,
    message: str,
) -> None:
    warnings.warn(
        f"{protocol_path} {endpoint} pin {pin.part.path}.{pin.name} {message}",
        ProtocolPinWarning,
        stacklevel=4,
    )


def infer_pin_roles(name: str, *, endpoint: str) -> frozenset[PinRole]:
    """Infer only well-known protocol roles from a pin name."""

    from .inference import infer_pin_roles as infer

    return infer(name, endpoint=endpoint)
