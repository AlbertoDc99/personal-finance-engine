"""Métricas de rendimiento (spec `investments.md` §9).

Convenciones documentadas:

- **Aportación neta** = aportaciones externas − retiradas externas. Las
  retiradas se registran con efectivo negativo, de modo que la suma de los
  flujos externos vigentes produce directamente la aportación neta.
- **Resultado del periodo** = ``V_fin − V_ini − C`` donde ``C`` es la
  aportación externa neta. Aportar 1.000 y terminar con 1.000 produce 0.
- **Cambio diario** = ``V_hoy − V_ayer − flujo externo del día`` (excluye
  aportaciones y retiradas del cambio de mercado).
- **TWR encadenada**: un flujo con solo fecha se considera al inicio del día,
  por lo que el retorno del día ``d`` es ``V_d / (V_{d-1} + F_d) − 1``.
  Los subperiodos se encadenan multiplicativamente.
- **XIRR**: aportaciones como flujos negativos, retiradas como positivos y el
  valor final de cartera como flujo terminal positivo. Base de tiempo
  ACT/365. Resolución por Newton con bisección de respaldo.

REGLA DURA: si la cobertura es insuficiente la métrica devuelve ``None`` con
motivo (envuelta en :class:`Metric`); jamás se publica un 0 inventado.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Generic, Sequence, TypeVar

from src.investments.domain.entities import InvestmentOperation
from src.investments.domain.enums import CoverageStatus, OperationKind
from src.investments.domain.errors import MonedaIncompatibleError, ValorInvalidoError
from src.investments.domain.projection import operaciones_vigentes
from src.investments.domain.values import Money

T = TypeVar("T")

_KINDS_FLUJO_EXTERNO = frozenset(
    {OperationKind.EXTERNAL_DEPOSIT, OperationKind.EXTERNAL_WITHDRAWAL}
)


@dataclass(frozen=True, slots=True)
class Metric(Generic[T]):
    """Resultado de una métrica con cobertura y motivo.

    ``value`` es ``None`` cuando la métrica no es calculable; en ese caso
    ``reason`` explica por qué. Un consumidor debe presentar ``None`` como
    ``—`` o «no calculable», nunca como cero.
    """

    value: T | None
    coverage: CoverageStatus
    reason: str | None = None

    @property
    def es_calculable(self) -> bool:
        """``True`` si la métrica tiene valor demostrable."""
        return self.value is not None


@dataclass(frozen=True, slots=True)
class PuntoDiario:
    """Valoración de cierre y flujo externo de un día de negocio.

    ``valor`` es ``None`` cuando ese día no tiene valoración demostrable.
    ``flujo_externo`` es el flujo neto del día (positivo al aportar,
    negativo al retirar), considerado al inicio del día por convención.
    """

    fecha: date
    valor: Money | None
    flujo_externo: Money


def aportacion_neta(
    operaciones: Sequence[InvestmentOperation],
    currency: str = "EUR",
) -> Metric[Money]:
    """Aportación externa neta: depósitos externos − retiradas externas.

    Solo cuentan operaciones vigentes (``booked`` y no reemplazadas) de tipo
    ``external_deposit`` o ``external_withdrawal``. Las retiradas llevan
    efectivo negativo, por lo que la suma directa produce la neta.
    """
    total = Decimal("0")
    for operacion in operaciones_vigentes(operaciones):
        if operacion.kind not in _KINDS_FLUJO_EXTERNO:
            continue
        for pata in operacion.legs:
            if pata.cash is not None and pata.cash.currency == currency:
                total += pata.cash.amount
    return Metric(
        value=Money(total, currency),
        coverage=CoverageStatus.COMPLETE,
    )


def resultado_periodo(
    v_ini: Money | None,
    v_fin: Money | None,
    aportacion: Money | None,
) -> Metric[Money]:
    """Resultado del periodo: ``V_fin − V_ini − C``.

    Si falta cualquiera de los tres componentes la métrica no es calculable
    (``None`` con motivo); no se sustituye una ausencia por cero.
    """
    if v_fin is None:
        return Metric(None, CoverageStatus.PARTIAL, "Valoración final no calculable.")
    if v_ini is None:
        return Metric(None, CoverageStatus.PARTIAL, "Valoración inicial no calculable.")
    if aportacion is None:
        return Metric(None, CoverageStatus.PARTIAL, "Aportación neta no calculable.")
    return Metric(
        value=v_fin - v_ini - aportacion,
        coverage=CoverageStatus.COMPLETE,
    )


def cambio_diario(
    v_hoy: Money | None,
    v_ayer: Money | None,
    flujo_externo: Money,
) -> Metric[Money]:
    """Cambio diario excluyendo flujos externos: ``V_hoy − V_ayer − F``.

    Una aportación no aparece como cambio favorable de mercado. Si falta una
    valoración, el cambio no es calculable.
    """
    if v_hoy is None or v_ayer is None:
        return Metric(
            None,
            CoverageStatus.PARTIAL,
            "Falta una valoración de cierre: cambio diario no calculable.",
        )
    return Metric(
        value=v_hoy - v_ayer - flujo_externo,
        coverage=CoverageStatus.COMPLETE,
    )


def twr_encadenada(puntos: Sequence[PuntoDiario]) -> Metric[Decimal]:
    """TWR encadenada sobre una serie diaria completa.

    Convención documentada: el flujo externo de cada día se considera al
    inicio del día, así que el retorno del día es
    ``V_d / (V_{d-1} + F_d) − 1`` y la TWR es el encadenamiento
    multiplicativo menos 1.

    REGLA DURA: si algún día del rango carece de valoración (``valor=None``)
    la TWR NO es calculable y se devuelve ``None`` con el motivo. Un hueco
    jamás se transforma en 0 %.
    """
    if len(puntos) < 2:
        return Metric(
            None,
            CoverageStatus.UNKNOWN,
            "Se necesitan al menos dos valoraciones para encadenar TWR.",
        )
    ordenados = sorted(puntos, key=lambda punto: punto.fecha)
    for punto in ordenados:
        if punto.valor is None:
            return Metric(
                None,
                CoverageStatus.PARTIAL,
                f"Valoración ausente el {punto.fecha.isoformat()}: "
                "TWR no calculable con hueco de cobertura.",
            )

    monedas = {punto.flujo_externo.currency for punto in ordenados}
    monedas.update(punto.valor.currency for punto in ordenados if punto.valor is not None)
    if len(monedas) != 1:
        raise MonedaIncompatibleError(
            "Todas las valoraciones y flujos de TWR deben compartir moneda."
        )
    factor = Decimal("1")
    for anterior, actual in zip(ordenados, ordenados[1:]):
        assert anterior.valor is not None and actual.valor is not None
        if actual.flujo_externo.currency != actual.valor.currency:
            raise MonedaIncompatibleError(
                "El flujo externo y la valoración deben compartir moneda."
            )
        base = anterior.valor.amount + actual.flujo_externo.amount
        if base <= 0:
            return Metric(
                None,
                CoverageStatus.PARTIAL,
                f"Base no válida ({base}) el {actual.fecha.isoformat()}: "
                "subperiodo sin base positiva, TWR no calculable.",
            )
        factor *= actual.valor.amount / base
    return Metric(value=factor - Decimal("1"), coverage=CoverageStatus.COMPLETE)


_DIAS_ANYO = Decimal("365")
_TOLERANCIA_NPV = Decimal("1e-9")
_MAX_ITERACIONES_NEWTON = 80
_MAX_ITERACIONES_BISECCION = 200


def _npv(tasa: Decimal, flujos: Sequence[tuple[Decimal, Decimal]]) -> Decimal:
    """Valor actual neto para una tasa anual (tiempos en años ACT/365)."""
    uno_mas_r = Decimal("1") + tasa
    total = Decimal("0")
    for tiempo, importe in flujos:
        total += importe * uno_mas_r ** (-tiempo)
    return total


def _derivada_npv(tasa: Decimal, flujos: Sequence[tuple[Decimal, Decimal]]) -> Decimal:
    uno_mas_r = Decimal("1") + tasa
    total = Decimal("0")
    for tiempo, importe in flujos:
        total += -tiempo * importe * uno_mas_r ** (-tiempo - Decimal("1"))
    return total


def xirr(
    flujos: Sequence[tuple[date, Money]],
    cobertura_completa: bool = True,
    motivo_cobertura: str | None = None,
) -> Metric[Decimal]:
    """XIRR anualizada de una serie de flujos fechados.

    Convención documentada: aportaciones negativas, retiradas positivas y el
    valor final de la cartera como flujo terminal positivo. Un flujo con solo
    fecha se considera al inicio de ese día. Base de tiempo ACT/365.

    Resolución numérica: Newton-Raphson con bisección de respaldo sobre el
    intervalo (−0,9999, 10).

    REGLA DURA: con ``cobertura_completa=False`` (hueco de flujos o
    valoraciones) se devuelve ``None`` con motivo; jamás un 0 inventado.
    """
    if not cobertura_completa:
        return Metric(
            None,
            CoverageStatus.PARTIAL,
            motivo_cobertura
            or "Cobertura insuficiente de flujos o valoraciones: XIRR no calculable.",
        )
    if len(flujos) < 2:
        return Metric(
            None,
            CoverageStatus.UNKNOWN,
            "Se necesitan al menos dos flujos fechados para calcular XIRR.",
        )
    monedas = {importe.currency for _, importe in flujos}
    if len(monedas) != 1:
        raise MonedaIncompatibleError(
            "Todos los flujos de XIRR deben compartir moneda."
        )
    importes = [importe.amount for _, importe in flujos]
    if not any(i < 0 for i in importes) or not any(i > 0 for i in importes):
        return Metric(
            None,
            CoverageStatus.UNKNOWN,
            "XIRR requiere al menos un flujo negativo y uno positivo.",
        )

    fecha_inicial = min(fecha for fecha, _ in flujos)
    if max(fecha for fecha, _ in flujos) == fecha_inicial:
        return Metric(None, CoverageStatus.UNKNOWN,
                      "XIRR no calculable sin intervalo temporal entre flujos.")
    serie = [
        (Decimal((fecha - fecha_inicial).days) / _DIAS_ANYO, importe.amount)
        for fecha, importe in flujos
    ]

    # Newton-Raphson
    tasa = Decimal("0.1")
    for _ in range(_MAX_ITERACIONES_NEWTON):
        valor = _npv(tasa, serie)
        if abs(valor) < _TOLERANCIA_NPV:
            return Metric(value=tasa, coverage=CoverageStatus.COMPLETE)
        derivada = _derivada_npv(tasa, serie)
        if derivada == 0:
            break
        siguiente = tasa - valor / derivada
        if siguiente <= Decimal("-0.9999") or siguiente > Decimal("1e6"):
            break
        tasa = siguiente

    # Bisección de respaldo: buscar un cambio de signo en (−0,9999, 10]
    inferior = Decimal("-0.9999")
    superior = Decimal("10")
    npv_inferior = _npv(inferior, serie)
    npv_superior = _npv(superior, serie)
    if npv_inferior * npv_superior > 0:
        paso = Decimal("0.25")
        encontrado = False
        cursor = inferior
        while cursor < superior:
            siguiente_cursor = min(cursor + paso, superior)
            if _npv(cursor, serie) * _npv(siguiente_cursor, serie) <= 0:
                inferior, superior = cursor, siguiente_cursor
                encontrado = True
                break
            cursor = siguiente_cursor
        if not encontrado:
            return Metric(
                None,
                CoverageStatus.UNKNOWN,
                "XIRR no converge: no se encontró raíz en el intervalo "
                "(−0,9999, 10].",
            )
    for _ in range(_MAX_ITERACIONES_BISECCION):
        medio = (inferior + superior) / 2
        npv_medio = _npv(medio, serie)
        if abs(npv_medio) < _TOLERANCIA_NPV:
            return Metric(value=medio, coverage=CoverageStatus.COMPLETE)
        if _npv(inferior, serie) * npv_medio <= 0:
            superior = medio
        else:
            inferior = medio
    return Metric(value=(inferior + superior) / 2, coverage=CoverageStatus.COMPLETE)
