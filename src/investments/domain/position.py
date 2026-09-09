"""Posición derivada y efectivo por moneda (spec `investments.md` §7).

Una posición se deriva de operaciones contabilizadas; el coste solo existe si
la fuente lo documenta. Sin coste demostrable NO se inventa P&L: los campos
de resultado permanecen ``None``.
"""

from __future__ import annotations

from dataclasses import dataclass

from src.investments.domain.errors import OperacionInvalidaError
from src.investments.domain.values import AccountId, InstrumentId, Money, Quantity


@dataclass(frozen=True, slots=True)
class Position:
    """Posición derivada por cuenta e instrumento.

    Invariante: si ``documented_cost`` es ``None`` (la fuente no demostró el
    coste), ``realized_result`` y ``unrealized_result`` deben ser ``None``.
    La aplicación nunca fabrica beneficio realizado/no realizado.
    """

    investment_account_id: AccountId
    instrument_id: InstrumentId
    quantity: Quantity
    documented_cost: Money | None = None
    realized_result: Money | None = None
    unrealized_result: Money | None = None

    def __post_init__(self) -> None:
        if self.documented_cost is None and (
            self.realized_result is not None or self.unrealized_result is not None
        ):
            raise OperacionInvalidaError(
                "Sin coste documentado por la fuente no puede existir "
                "resultado realizado/no realizado: no se inventa P&L."
            )


@dataclass(frozen=True, slots=True)
class CashBalance:
    """Saldo de efectivo de la cartera en una moneda concreta.

    El efectivo del bróker es parte de la cartera; no se oculta ni se
    clasifica como posición de mercado.
    """

    balance: Money

    @property
    def currency(self) -> str:
        """Moneda ISO 4217 del saldo."""
        return self.balance.currency
