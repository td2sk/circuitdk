from __future__ import annotations

from ..constructs import Construct, Part, Pin
from .common import PinRole, PinSelector, resolve_protocol_pin


class UART(Construct):
    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        left: Part | None = None,
        left_tx: PinSelector | None = None,
        left_rx: PinSelector | None = None,
        right: Part | None = None,
        right_tx: PinSelector | None = None,
        right_rx: PinSelector | None = None,
    ) -> None:
        super().__init__(scope, construct_id)
        if (left_tx is None) != (right_rx is None):
            raise ValueError("left_tx and right_rx must be specified together")
        if (left_rx is None) != (right_tx is None):
            raise ValueError("left_rx and right_tx must be specified together")
        if left_tx is None and left_rx is None:
            raise ValueError("UART requires at least one data direction")

        self.left = left
        self.right = right
        self.left_tx = self._optional(left, left_tx, PinRole.UART_TX, "left")
        self.left_rx = self._optional(left, left_rx, PinRole.UART_RX, "left")
        self.right_tx = self._optional(right, right_tx, PinRole.UART_TX, "right")
        self.right_rx = self._optional(right, right_rx, PinRole.UART_RX, "right")
        if self.left_tx is not None and self.right_rx is not None:
            self.circuit.connect(self.left_tx, self.right_rx)
        if self.left_rx is not None and self.right_tx is not None:
            self.circuit.connect(self.left_rx, self.right_tx)

    def _optional(
        self,
        owner: Part | None,
        selector: PinSelector | None,
        role: PinRole,
        endpoint: str,
    ) -> Pin | None:
        if selector is None:
            return None
        return resolve_protocol_pin(
            circuit=self.circuit,
            owner=owner,
            selector=selector,
            expected_role=role,
            endpoint=endpoint,
            protocol_path=self.path,
        )
