"""Cobertura de datos por dimensión (spec `investments.md` §10).

Cada día conserva cobertura independiente para operaciones, posiciones,
precios y FX. Una métrica solo es calculable cuando todas las dimensiones que
necesita están completas en el rango; en caso contrario se devuelve el motivo
y la métrica queda como no calculable (nunca cero).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Iterable, Sequence

from src.investments.domain.enums import CoverageStatus
from src.investments.domain.errors import ValorInvalidoError


class CoverageDimension(str, Enum):
    """Dimensiones independientes de cobertura."""

    OPERATIONS = "operaciones"
    POSITIONS = "posiciones"
    PRICES = "precios"
    FX = "fx"


@dataclass(frozen=True, slots=True)
class CoverageInterval:
    """Intervalo de cobertura declarado para una dimensión concreta.

    ``start`` y ``end`` son fechas de negocio inclusivas.
    """

    dimension: CoverageDimension
    start: date
    end: date
    status: CoverageStatus

    def __post_init__(self) -> None:
        if self.start > self.end:
            raise ValorInvalidoError(
                f"Intervalo de cobertura inválido: {self.start} > {self.end}."
            )

    def cubre(self, fecha: date) -> bool:
        """``True`` si la fecha cae dentro del intervalo (inclusivo)."""
        return self.start <= fecha <= self.end


def _dias(inicio: date, fin: date) -> Iterable[date]:
    actual = inicio
    while actual <= fin:
        yield actual
        actual += timedelta(days=1)


def evaluar_dimension(
    intervalos: Sequence[CoverageInterval],
    dimension: CoverageDimension,
    inicio: date,
    fin: date,
) -> CoverageStatus:
    """Evalúa la cobertura de una dimensión en un rango de fechas de negocio.

    - ``complete``: todos los días del rango están cubiertos por intervalos
      declarados completos.
    - ``partial``: solo parte del rango está cubierta (completa o parcial).
    - ``unknown``: ningún dato de cobertura alcanza el rango.
    """
    if inicio > fin:
        raise ValorInvalidoError(f"Rango inválido: {inicio} > {fin}.")
    relevantes = [i for i in intervalos if i.dimension is dimension]
    completos = [i for i in relevantes if i.status is CoverageStatus.COMPLETE]

    dias_totales = 0
    dias_completos = 0
    dias_tocados = 0
    for dia in _dias(inicio, fin):
        dias_totales += 1
        if any(i.cubre(dia) for i in completos):
            dias_completos += 1
        if any(i.cubre(dia) for i in relevantes):
            dias_tocados += 1

    if dias_completos == dias_totales:
        return CoverageStatus.COMPLETE
    if dias_tocados > 0:
        return CoverageStatus.PARTIAL
    return CoverageStatus.UNKNOWN


def es_metrica_calculable(
    intervalos: Sequence[CoverageInterval],
    dimensiones_requeridas: Sequence[CoverageDimension],
    inicio: date,
    fin: date,
) -> tuple[bool, str | None]:
    """Decide si una métrica es calculable en el rango dado.

    Devuelve ``(True, None)`` solo si todas las dimensiones requeridas están
    completas. En caso contrario devuelve ``(False, motivo)`` con la primera
    dimensión insuficiente; el consumidor debe presentar la métrica como no
    calculable (``—``), jamás como cero.
    """
    for dimension in dimensiones_requeridas:
        estado = evaluar_dimension(intervalos, dimension, inicio, fin)
        if estado is not CoverageStatus.COMPLETE:
            return (
                False,
                f"Cobertura {estado.value} en la dimensión "
                f"'{dimension.value}' para el rango {inicio}..{fin}.",
            )
    return True, None
