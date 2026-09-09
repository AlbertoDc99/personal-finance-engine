"""Valoración diaria de cierre (spec `investments.md` §8.2).

Fórmulas:

    Valor instrumento(d) = cantidad(d) × precio efectivo(d) × FX a EUR(d)
    Valor cartera(d)     = efectivo convertido(d) + Σ Valor instrumento(d)

Reglas duras:

- El arrastre del último precio conocido es explícito
  (``ValuationState.CARRIED_FORWARD``) y conserva la fecha efectiva real del
  precio: nunca se presenta como una cotización nueva.
- Un precio ausente hace el componente NO calculable (``None``) y el total
  pasa a estado parcial. NUNCA se sustituye por cero.
- Se conservan precio, valor y moneda nativos, además del FX aplicado con su
  fecha efectiva y procedencia. Un tipo actual jamás reescribe una
  valoración histórica.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from types import MappingProxyType
from typing import Mapping, Sequence

from src.investments.domain.entities import FxObservation, PriceObservation
from src.investments.domain.enums import CoverageStatus, ValuationState
from src.investments.domain.position import Position
from src.investments.domain.projection import ProjectionResult
from src.investments.domain.values import FxRate, InstrumentId, Money

MONEDA_BASE_POR_DEFECTO = "EUR"


@dataclass(frozen=True, slots=True)
class ValuationIndex:
    """Índice inmutable para resolver precios y FX por fecha en O(log n).

    La serie histórica consulta el mismo conjunto de observaciones miles de
    veces. Mantenerlas agrupadas y ordenadas evita recorrer todo el histórico
    para cada instrumento y para cada día, sin cambiar la regla de selección.
    """

    prices: Mapping[InstrumentId, tuple[PriceObservation, ...]]
    price_dates: Mapping[InstrumentId, tuple[date, ...]]
    fxs: Mapping[tuple[str, str], tuple[FxObservation, ...]]
    fx_dates: Mapping[tuple[str, str], tuple[date, ...]]

    def effective_price(
        self, instrument_id: InstrumentId, fecha: date
    ) -> PriceObservation | None:
        observations = self.prices.get(instrument_id, ())
        dates = self.price_dates.get(instrument_id, ())
        index = bisect_right(dates, fecha) - 1
        return observations[index] if index >= 0 else None

    def effective_fx(
        self, base_currency: str, quote_currency: str, fecha: date
    ) -> FxObservation | None:
        pair = (base_currency, quote_currency)
        observations = self.fxs.get(pair, ())
        dates = self.fx_dates.get(pair, ())
        index = bisect_right(dates, fecha) - 1
        return observations[index] if index >= 0 else None


def construir_indice_valoracion(
    precios: Sequence[PriceObservation],
    fxs: Sequence[FxObservation],
) -> ValuationIndex:
    """Agrupa observaciones conservando la revisión más reciente del día."""

    prices_mutable: dict[InstrumentId, list[PriceObservation]] = {}
    for observation in precios:
        prices_mutable.setdefault(observation.instrument_id, []).append(observation)
    prices_indexed = {
        instrument_id: tuple(
            sorted(items, key=lambda item: (item.effective_date, item.received_at))
        )
        for instrument_id, items in prices_mutable.items()
    }

    fxs_mutable: dict[tuple[str, str], list[FxObservation]] = {}
    for observation in fxs:
        pair = (observation.base_currency, observation.quote_currency)
        fxs_mutable.setdefault(pair, []).append(observation)
    fxs_indexed = {
        pair: tuple(
            sorted(items, key=lambda item: (item.effective_date, item.received_at))
        )
        for pair, items in fxs_mutable.items()
    }

    return ValuationIndex(
        prices=MappingProxyType(prices_indexed),
        price_dates=MappingProxyType(
            {
                instrument_id: tuple(item.effective_date for item in items)
                for instrument_id, items in prices_indexed.items()
            }
        ),
        fxs=MappingProxyType(fxs_indexed),
        fx_dates=MappingProxyType(
            {
                pair: tuple(item.effective_date for item in items)
                for pair, items in fxs_indexed.items()
            }
        ),
    )


@dataclass(frozen=True, slots=True)
class InstrumentValuation:
    """Valoración de un instrumento en una fecha de negocio concreta.

    Conserva los datos nativos (precio, moneda, valor) y el FX aplicado.
    ``price_effective_date`` es la fecha real del precio usado, que puede ser
    anterior a ``valuation_date`` cuando el estado es ``carried_forward``.
    """

    instrument_id: InstrumentId
    valuation_date: date
    quantity: Decimal
    state: ValuationState
    price: Decimal | None = None
    price_currency: str | None = None
    price_kind: str | None = None
    price_provider: str | None = None
    price_effective_date: date | None = None
    native_value: Money | None = None
    fx_applied: FxRate | None = None
    value_base: Money | None = None
    reason: str | None = None

    @property
    def es_calculable(self) -> bool:
        """``True`` si el componente tiene valor consolidado calculable."""
        return self.value_base is not None


@dataclass(frozen=True, slots=True)
class PortfolioValuation:
    """Valoración de la cartera completa en una fecha de negocio.

    - ``known_value``: suma de los componentes demostrables (instrumentos con
      valor calculable + efectivo convertible). Es un valor parcial cuando
      falta algún componente.
    - ``total``: solo existe (no ``None``) cuando el estado es ``complete``.
      Un total parcial nunca se presenta como total: la ausencia no es cero.
    """

    valuation_date: date
    base_currency: str
    instruments: tuple[InstrumentValuation, ...]
    cash_base: Money | None
    known_value: Money
    total: Money | None
    status: CoverageStatus
    missing_components: tuple[str, ...] = ()


def precio_efectivo(
    observaciones: Sequence[PriceObservation],
    instrument_id: InstrumentId,
    fecha: date,
    indice: ValuationIndex | None = None,
) -> PriceObservation | None:
    """Último precio publicado con fecha efectiva menor o igual a ``fecha``.

    Entre observaciones del mismo día prevalece la recibida más tarde
    (revisión más reciente). Devuelve ``None`` si no hay precio aplicable:
    la ausencia nunca se rellena con un valor inventado.
    """
    if indice is not None:
        return indice.effective_price(instrument_id, fecha)
    candidatas = [
        obs
        for obs in observaciones
        if obs.instrument_id == instrument_id and obs.effective_date <= fecha
    ]
    if not candidatas:
        return None
    return max(candidatas, key=lambda obs: (obs.effective_date, obs.received_at))


def fx_efectivo(
    observaciones: Sequence[FxObservation],
    base_currency: str,
    quote_currency: str,
    fecha: date,
    indice: ValuationIndex | None = None,
) -> FxObservation | None:
    """Última observación FX del par con fecha efectiva ≤ ``fecha``."""
    if indice is not None:
        return indice.effective_fx(base_currency, quote_currency, fecha)
    candidatas = [
        obs
        for obs in observaciones
        if obs.base_currency == base_currency
        and obs.quote_currency == quote_currency
        and obs.effective_date <= fecha
    ]
    if not candidatas:
        return None
    return max(candidatas, key=lambda obs: (obs.effective_date, obs.received_at))


def valorar_instrumento(
    posicion: Position,
    precios: Sequence[PriceObservation],
    fxs: Sequence[FxObservation],
    fecha: date,
    base_currency: str = MONEDA_BASE_POR_DEFECTO,
    indice: ValuationIndex | None = None,
) -> InstrumentValuation:
    """Valora una posición en la fecha indicada.

    - Si hay precio con fecha efectiva igual a ``fecha``: estado ``fresh``.
    - Si el precio aplicable es anterior: estado ``carried_forward``,
      conservando su fecha efectiva real.
    - Sin precio aplicable: estado ``missing``, valor ``None`` (nunca cero).
    - Con precio en moneda distinta de la base y sin FX aplicable, el valor
      consolidado tampoco es calculable.
    """
    observacion = precio_efectivo(
        precios, posicion.instrument_id, fecha, indice=indice
    )
    if observacion is None:
        return InstrumentValuation(
            instrument_id=posicion.instrument_id,
            valuation_date=fecha,
            quantity=posicion.quantity.value,
            state=ValuationState.MISSING,
            reason="Precio ausente: componente no calculable (nunca cero).",
        )

    estado = (
        ValuationState.FRESH
        if observacion.effective_date == fecha
        else ValuationState.CARRIED_FORWARD
    )
    valor_nativo = Money(
        posicion.quantity.value * observacion.price, observacion.currency
    )

    fx_aplicado: FxRate | None = None
    valor_base: Money | None
    motivo: str | None = None
    if observacion.currency == base_currency:
        valor_base = valor_nativo
    else:
        observacion_fx = fx_efectivo(
            fxs, observacion.currency, base_currency, fecha, indice=indice
        )
        if observacion_fx is None:
            valor_base = None
            motivo = (
                f"FX {observacion.currency}/{base_currency} ausente: "
                "valor consolidado no calculable (nunca cero)."
            )
        else:
            fx_aplicado = observacion_fx.como_tipo()
            valor_base = fx_aplicado.convertir(valor_nativo)

    return InstrumentValuation(
        instrument_id=posicion.instrument_id,
        valuation_date=fecha,
        quantity=posicion.quantity.value,
        state=estado,
        price=observacion.price,
        price_currency=observacion.currency,
        price_kind=observacion.kind.value,
        price_provider=observacion.provider,
        price_effective_date=observacion.effective_date,
        native_value=valor_nativo,
        fx_applied=fx_aplicado,
        value_base=valor_base,
        reason=motivo,
    )


def valorar_cartera(
    proyeccion: ProjectionResult,
    precios: Sequence[PriceObservation],
    fxs: Sequence[FxObservation],
    fecha: date,
    base_currency: str = MONEDA_BASE_POR_DEFECTO,
    indice: ValuationIndex | None = None,
) -> PortfolioValuation:
    """Valora la cartera completa (instrumentos + efectivo) en ``fecha``.

    El efectivo en moneda distinta de la base se convierte con la observación
    FX aplicable; si falta, ese componente también queda no calculable y el
    estado del total pasa a parcial. Un total parcial se expone como
    ``known_value`` (valor demostrable) con ``total=None``.
    """
    componentes = tuple(
        valorar_instrumento(
            posicion, precios, fxs, fecha, base_currency, indice=indice
        )
        for posicion in proyeccion.positions.values()
    )
    faltantes: list[str] = [
        str(componente.instrument_id)
        for componente in componentes
        if not componente.es_calculable
    ]

    efectivo_conocido = Decimal("0")
    efectivo_completo = True
    for moneda, saldo in proyeccion.cash.items():
        if moneda == base_currency:
            efectivo_conocido += saldo.balance.amount
        else:
            observacion_fx = fx_efectivo(
                fxs, moneda, base_currency, fecha, indice=indice
            )
            if observacion_fx is None:
                efectivo_completo = False
                faltantes.append(f"efectivo:{moneda}")
            else:
                convertido = observacion_fx.como_tipo().convertir(saldo.balance)
                efectivo_conocido += convertido.amount

    valor_instrumentos = sum(
        (
            componente.value_base.amount
            for componente in componentes
            if componente.value_base is not None
        ),
        Decimal("0"),
    )
    valor_conocido = Money(efectivo_conocido + valor_instrumentos, base_currency)
    estado = CoverageStatus.COMPLETE if not faltantes else CoverageStatus.PARTIAL
    return PortfolioValuation(
        valuation_date=fecha,
        base_currency=base_currency,
        instruments=componentes,
        cash_base=Money(efectivo_conocido, base_currency) if efectivo_completo else None,
        known_value=valor_conocido,
        total=valor_conocido if estado is CoverageStatus.COMPLETE else None,
        status=estado,
        missing_components=tuple(faltantes),
    )
