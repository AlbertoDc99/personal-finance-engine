"""Proyección de posiciones y efectivo desde operaciones contabilizadas.

Servicio puro (spec `investments.md` §7 y §10):

- Solo cuentan operaciones con estado ``booked``; las ``pending`` y
  ``cancelled`` NO afectan al estado derivado.
- Una corrección se resuelve a la revisión vigente: la operación reemplazada
  (referenciada por ``supersedes_operation_id`` de otra) queda excluida y no
  se duplica ningún hecho.
- Las operaciones se aplican ordenadas por fecha efectiva de negocio.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Sequence

from src.investments.domain.entities import InvestmentOperation
from src.investments.domain.enums import OperationStatus
from src.investments.domain.position import CashBalance, Position
from src.investments.domain.values import InstrumentId, Money, Quantity


@dataclass(frozen=True)
class ProjectionResult:
    """Estado derivado de la cartera: posiciones por instrumento y efectivo
    por moneda. Es un resultado inmutable de un cálculo puro."""

    positions: Mapping[InstrumentId, Position] = field(default_factory=dict)
    cash: Mapping[str, CashBalance] = field(default_factory=dict)

    def efectivo(self, currency: str) -> Money:
        """Saldo de efectivo en la moneda pedida (cero si no hay movimientos)."""
        saldo = self.cash.get(currency)
        if saldo is None:
            return Money.cero(currency)
        return saldo.balance


def operaciones_vigentes(
    operaciones: Sequence[InvestmentOperation],
) -> list[InvestmentOperation]:
    """Resuelve el conjunto de operaciones que cuentan para la proyección.

    - Excluye ``pending`` y ``cancelled``.
    - Excluye las revisiones reemplazadas: si una operación es referenciada
      por el ``supersedes_operation_id`` de otra, solo cuenta la revisión
      vigente (sin duplicar).
    - Devuelve la lista ordenada por ``effective_date`` (orden estable).
    """
    reemplazadas = {
        op.supersedes_operation_id
        for op in operaciones
        if op.supersedes_operation_id is not None
    }
    vigentes = [
        op
        for op in operaciones
        if op.status is OperationStatus.BOOKED and op.operation_id not in reemplazadas
    ]
    return sorted(vigentes, key=lambda op: op.effective_date)


def proyectar_operaciones(
    operaciones: Sequence[InvestmentOperation],
    hasta: date | None = None,
) -> ProjectionResult:
    """Proyecta posiciones y efectivo desde operaciones contabilizadas.

    Aplica las patas de cada operación vigente en orden de fecha efectiva:

    - los componentes de efectivo (``cash``, ``fee``, ``tax``) se acumulan
      por moneda con su signo;
    - las cantidades firmadas de instrumento se acumulan por instrumento.

    Si se indica ``hasta``, solo cuentan las operaciones con fecha efectiva
    menor o igual a esa fecha de negocio.
    """
    efectivo_por_moneda: dict[str, Decimal] = {}
    cantidad_por_instrumento: dict[InstrumentId, Decimal] = {}
    cuenta_por_instrumento: dict[InstrumentId, str] = {}
    coste_por_instrumento: dict[InstrumentId, Money] = {}

    for operacion in operaciones_vigentes(operaciones):
        if hasta is not None and operacion.effective_date > hasta:
            continue
        for pata in operacion.legs:
            for componente in (pata.cash, pata.fee, pata.tax):
                if componente is not None:
                    acumulado = efectivo_por_moneda.get(
                        componente.currency, Decimal("0")
                    )
                    efectivo_por_moneda[componente.currency] = (
                        acumulado + componente.amount
                    )
            if pata.quantity is not None and pata.instrument_id is not None:
                acumulada = cantidad_por_instrumento.get(
                    pata.instrument_id, Decimal("0")
                )
                cantidad_por_instrumento[pata.instrument_id] = (
                    acumulada + pata.quantity.value
                )
                cuenta_por_instrumento[pata.instrument_id] = (
                    operacion.investment_account_id
                )
                if pata.documented_cost is not None:
                    anterior = coste_por_instrumento.get(pata.instrument_id)
                    if anterior is None:
                        coste_por_instrumento[pata.instrument_id] = pata.documented_cost
                    else:
                        coste_por_instrumento[pata.instrument_id] = (
                            anterior + pata.documented_cost
                        )

    posiciones = {
        instrument_id: Position(
            investment_account_id=cuenta_por_instrumento[instrument_id],  # type: ignore[arg-type]
            instrument_id=instrument_id,
            quantity=Quantity(cantidad),
            documented_cost=coste_por_instrumento.get(instrument_id),
        )
        for instrument_id, cantidad in cantidad_por_instrumento.items()
    }
    efectivo = {
        moneda: CashBalance(balance=Money(importe, moneda))
        for moneda, importe in efectivo_por_moneda.items()
    }
    return ProjectionResult(
        positions=MappingProxyType(posiciones),
        cash=MappingProxyType(efectivo),
    )
