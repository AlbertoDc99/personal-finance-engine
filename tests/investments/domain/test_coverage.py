"""Tests de cobertura por dimensión y calculabilidad de métricas."""

from datetime import date

from src.investments.domain.coverage import (
    CoverageDimension,
    CoverageInterval,
    es_metrica_calculable,
    evaluar_dimension,
)
from src.investments.domain.enums import CoverageStatus


def _intervalo(
    dimension: CoverageDimension,
    inicio: date,
    fin: date,
    status: CoverageStatus = CoverageStatus.COMPLETE,
) -> CoverageInterval:
    return CoverageInterval(dimension=dimension, start=inicio, end=fin, status=status)


class TestEvaluarDimension:
    def test_rango_totalmente_cubierto_es_complete(self) -> None:
        intervalos = [
            _intervalo(CoverageDimension.PRICES, date(2026, 1, 1), date(2026, 1, 31))
        ]
        estado = evaluar_dimension(
            intervalos, CoverageDimension.PRICES, date(2026, 1, 10), date(2026, 1, 20)
        )
        assert estado is CoverageStatus.COMPLETE

    def test_rango_parcialmente_cubierto_es_partial(self) -> None:
        intervalos = [
            _intervalo(CoverageDimension.PRICES, date(2026, 1, 1), date(2026, 1, 15))
        ]
        estado = evaluar_dimension(
            intervalos, CoverageDimension.PRICES, date(2026, 1, 10), date(2026, 1, 20)
        )
        assert estado is CoverageStatus.PARTIAL

    def test_sin_datos_es_unknown(self) -> None:
        estado = evaluar_dimension(
            [], CoverageDimension.FX, date(2026, 1, 1), date(2026, 1, 5)
        )
        assert estado is CoverageStatus.UNKNOWN

    def test_intervalo_declarado_parcial_no_cuenta_como_completo(self) -> None:
        intervalos = [
            _intervalo(
                CoverageDimension.OPERATIONS,
                date(2026, 1, 1),
                date(2026, 1, 31),
                status=CoverageStatus.PARTIAL,
            )
        ]
        estado = evaluar_dimension(
            intervalos, CoverageDimension.OPERATIONS, date(2026, 1, 5), date(2026, 1, 10)
        )
        assert estado is CoverageStatus.PARTIAL

    def test_las_dimensiones_son_independientes(self) -> None:
        """Cobertura completa de precios no implica cobertura de FX."""
        intervalos = [
            _intervalo(CoverageDimension.PRICES, date(2026, 1, 1), date(2026, 1, 31))
        ]
        assert (
            evaluar_dimension(
                intervalos, CoverageDimension.FX, date(2026, 1, 5), date(2026, 1, 10)
            )
            is CoverageStatus.UNKNOWN
        )


class TestMetricaCalculable:
    def test_todas_las_dimensiones_completas(self) -> None:
        intervalos = [
            _intervalo(CoverageDimension.OPERATIONS, date(2026, 1, 1), date(2026, 1, 31)),
            _intervalo(CoverageDimension.PRICES, date(2026, 1, 1), date(2026, 1, 31)),
        ]
        calculable, motivo = es_metrica_calculable(
            intervalos,
            [CoverageDimension.OPERATIONS, CoverageDimension.PRICES],
            date(2026, 1, 5),
            date(2026, 1, 20),
        )
        assert calculable is True
        assert motivo is None

    def test_dimension_insuficiente_da_motivo(self) -> None:
        intervalos = [
            _intervalo(CoverageDimension.OPERATIONS, date(2026, 1, 1), date(2026, 1, 31)),
        ]
        calculable, motivo = es_metrica_calculable(
            intervalos,
            [CoverageDimension.OPERATIONS, CoverageDimension.PRICES],
            date(2026, 1, 5),
            date(2026, 1, 20),
        )
        assert calculable is False
        assert motivo is not None
        assert "precios" in motivo
