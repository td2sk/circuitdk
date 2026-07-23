from __future__ import annotations

import re

from .common import PinRole

_SPI_CLOCK = frozenset({"SCK", "SCLK", "SPICLK", "SPI_CLK", "SPI_SCK"})
_SPI_CONTROLLER_OUT = frozenset({"MOSI", "COPI", "PICO"})
_SPI_CONTROLLER_IN = frozenset({"MISO", "CIPO", "POCI"})
_DEVICE_INPUT = frozenset({"SDI", "DIN", "SI"})
_DEVICE_OUTPUT = frozenset({"SDO", "DOUT", "SO"})
_SPI_SELECT = frozenset({"CS", "NCS", "NSS", "SS", "CSB", "CS_N"})
_I2C_CLOCK = frozenset({"SCL", "I2CSCL", "I2C_SCL"})
_I2C_DATA = frozenset({"SDA", "I2CSDA", "I2C_SDA"})
_UART_TX = frozenset({"TX", "TXD", "UARTTX", "UART_TX"})
_UART_RX = frozenset({"RX", "RXD", "UARTRX", "UART_RX"})


def infer_pin_roles(name: str, *, endpoint: str) -> frozenset[PinRole]:
    candidates = _name_candidates(name)
    roles: set[PinRole] = set()
    if candidates & _SPI_CLOCK:
        roles.add(PinRole.SPI_CLOCK)
    if candidates & _SPI_CONTROLLER_OUT:
        roles.add(PinRole.SPI_CONTROLLER_OUT)
    if candidates & _SPI_CONTROLLER_IN:
        roles.add(PinRole.SPI_CONTROLLER_IN)
    if candidates & _DEVICE_INPUT:
        roles.add(
            PinRole.SPI_CONTROLLER_IN if endpoint == "controller" else PinRole.SPI_CONTROLLER_OUT
        )
    if candidates & _DEVICE_OUTPUT:
        roles.add(
            PinRole.SPI_CONTROLLER_OUT if endpoint == "controller" else PinRole.SPI_CONTROLLER_IN
        )
    if candidates & _SPI_SELECT:
        roles.add(PinRole.SPI_CHIP_SELECT)
    if candidates & _I2C_CLOCK:
        roles.add(PinRole.I2C_CLOCK)
    if candidates & _I2C_DATA:
        roles.add(PinRole.I2C_DATA)
    if candidates & _UART_TX:
        roles.add(PinRole.UART_TX)
    if candidates & _UART_RX:
        roles.add(PinRole.UART_RX)
    return frozenset(roles)


def _name_candidates(name: str) -> frozenset[str]:
    normalized = name.upper().strip()
    normalized = normalized.lstrip("~#")
    alpha_tokens = tuple(re.findall(r"[A-Z]+", normalized))
    if not alpha_tokens:
        return frozenset()

    candidates = set(alpha_tokens)
    candidates.add("_".join(alpha_tokens))
    candidates.add("".join(alpha_tokens))

    if alpha_tokens[0] in {"SPI", "I", "UART"} and len(alpha_tokens) > 1:
        suffix = alpha_tokens[1:]
        candidates.add("_".join(suffix))
        candidates.add("".join(suffix))

    if len(alpha_tokens) == 2 and alpha_tokens[-1] == "N":
        candidates.add(alpha_tokens[0])
    return frozenset(candidates)
