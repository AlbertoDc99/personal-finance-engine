"""Tests de rendimiento: aportación neta, resultado, cambio diario, TWR y XIRR.

REGLA DURA verificada: cobertura insuficiente → ``None`` con motivo, jamás 0.
"""

from datetime import date
from decimal import Decimal

from src.investments.domain.enums import CoverageStatus
from src.investments.domain.performance import (
    PuntoDiario,
    aportacion_neta,
    cambio_diario,
    resultado_periodo,
    twr_encadenada,
    xirr,
)
from src.investments.domain.values import Money

from .helpers_fixtures import cargar_fixture, construir_operaciones_happy_path


def _eur(importe: str) -> Money:
    return Money(Decimal(importe), "EUR")


class TestAportacionNeta:
    def test_happy_path_exacto(self) -> None:
        """Fixture: 1500 aportados − 250 retirados = 1250.00."""
        data = cargar_fixture("portfolio_happy_path.json")
        operaciones = construir_operaciones_happy_path(data)
        metrica = aportacion_neta(operaciones)
        assert metrica.es_calculable
        assert metrica.value == _eur(data["expected"]["net_external_contribution_eur"])

    def test_operaciones_internas_no_cuentan(self) -> None:
        """Compras, comisiones y dividendos no alteran la aportación neta."""
        data = cargar_fixture("portfolio_happy_path.json")
        operaciones = construir_operaciones_happy_path(data)
        internas = [
            op
            for op in operaciones
            if op.kind.value not in ("external_deposit", "external_withdrawal")
        ]
        metrica = aportacion_neta(internas)
        assert metrica.value == _eur("0")


class TestResultadoPeriodo:
    def test_happy_path_exacto(self) -> None:
        """Fixture: V_fin=1313, V_ini=0, C=1250 → resultado 63.00."""
        data = cargar_fixture("portfolio_happy_path.json")
        esperado = data["expected"]
        metrica = resultado_periodo(
            v_ini=_eur("0"),
            v_fin=_eur(esperado["portfolio_value_eur"]),
            aportacion=_eur(esperado["net_external_contribution_eur"]),
        )
        assert metrica.es_calculable
        assert metrica.value == _eur(esperado["result_eur"])

    def test_aportar_1000_y_terminar_en_1000_es_resultado_cero(self) -> None:
        """AC-INV-009: la aportación no aparece como ganancia."""
        metrica = resultado_periodo(
            v_ini=_eur("0"), v_fin=_eur("1000.00"), aportacion=_eur("1000.00")
        )
        assert metrica.es_calculable
        assert metrica.value == _eur("0.00")

    def test_valoracion_ausente_no_es_cero(self) -> None:
        metrica = resultado_periodo(v_ini=None, v_fin=_eur("1000"), aportacion=_eur("0"))
        assert metrica.value is None
        assert metrica.coverage is CoverageStatus.PARTIAL
        assert metrica.reason is not None


class TestCambioDiario:
    def test_excluye_flujos_externos(self) -> None:
        """AC-INV-010: V_ini=1000, aportación 200, V_fin=1230 → resultado 30."""
        metrica = cambio_diario(
            v_hoy=_eur("1230.00"), v_ayer=_eur("1000.00"), flujo_externo=_eur("200.00")
        )
        assert metrica.value == _eur("30.00")

    def test_sin_valoracion_no_es_calculable(self) -> None:
        metrica = cambio_diario(v_hoy=None, v_ayer=_eur("1000"), flujo_externo=_eur("0"))
        assert metrica.value is None
        assert metrica.coverage is CoverageStatus.PARTIAL


class TestTwr:
    def test_twr_sin_flujos(self) -> None:
        puntos = [
            PuntoDiario(date(2026, 1, 1), _eur("1000.00"), _eur("0")),
            PuntoDiario(date(2026, 1, 2), _eur("1100.00"), _eur("0")),
        ]
        metrica = twr_encadenada(puntos)
        assert metrica.es_calculable
        assert metrica.value == Decimal("0.1")

    def test_twr_neutraliza_flujo_al_inicio_del_dia(self) -> None:
        """Convención: flujo con solo fecha → inicio del día.
        1210 / (1000 + 100) − 1 = 10 %."""
        puntos = [
            PuntoDiario(date(2026, 1, 1), _eur("1000.00"), _eur("0")),
            PuntoDiario(date(2026, 1, 2), _eur("1210.00"), _eur("100.00")),
        ]
        metrica = twr_encadenada(puntos)
        assert metrica.value == Decimal("0.1")

    def test_hueco_de_valoracion_devuelve_none(self) -> None:
        """Un día sin base válida no se transforma en 0 %."""
        puntos = [
            PuntoDiario(date(2026, 1, 1), _eur("1000.00"), _eur("0")),
            PuntoDiario(date(2026, 1, 2), None, _eur("0")),
            PuntoDiario(date(2026, 1, 3), _eur("1100.00"), _eur("0")),
        ]
        metrica = twr_encadenada(puntos)
        assert metrica.value is None
        assert metrica.coverage is CoverageStatus.PARTIAL
        assert "2026-01-02" in (metrica.reason or "")

    def test_menos_de_dos_puntos_no_es_calculable(self) -> None:
        metrica = twr_encadenada([PuntoDiario(date(2026, 1, 1), _eur("1000"), _eur("0"))])
        assert metrica.value is None
        assert metrica.coverage is CoverageStatus.UNKNOWN


class TestXirr:
    def test_un_anyo_exacto(self) -> None:
        """−1000 el día 0 y +1100 a los 365 días (ACT/365) → 10 % anual."""
        flujos = [
            (date(2026, 1, 1), _eur("-1000.00")),
            (date(2027, 1, 1), _eur("1100.00")),
        ]
        metrica = xirr(flujos)
        assert metrica.es_calculable
        assert metrica.value is not None
        assert abs(metrica.value - Decimal("0.10")) < Decimal("0.000001")

    def test_aportar_y_terminar_igual_es_tasa_cero(self) -> None:
        flujos = [
            (date(2026, 1, 1), _eur("-1000.00")),
            (date(2026, 7, 1), _eur("1000.00")),
        ]
        metrica = xirr(flujos)
        assert metrica.es_calculable
        assert metrica.value is not None
        assert abs(metrica.value) < Decimal("0.000001")

    def test_hueco_de_cobertura_devuelve_none(self) -> None:
        """REGLA DURA: cobertura insuficiente → None con motivo, jamás 0."""
        flujos = [
            (date(2026, 1, 1), _eur("-1000.00")),
            (date(2027, 1, 1), _eur("1100.00")),
        ]
        metrica = xirr(
            flujos,
            cobertura_completa=False,
            motivo_cobertura="Falta un flujo intermedio demostrable.",
        )
        assert metrica.value is None
        assert metrica.coverage is CoverageStatus.PARTIAL
        assert metrica.reason == "Falta un flujo intermedio demostrable."

    def test_sin_flujos_de_ambos_signos_no_es_calculable(self) -> None:
        flujos = [
            (date(2026, 1, 1), _eur("-1000.00")),
            (date(2026, 6, 1), _eur("-500.00")),
        ]
        metrica = xirr(flujos)
        assert metrica.value is None
        assert metrica.coverage is CoverageStatus.UNKNOWN
