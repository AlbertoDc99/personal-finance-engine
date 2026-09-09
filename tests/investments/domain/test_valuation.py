"""Tests de valoración diaria: FX reproducible, arrastre y precio ausente.

Verifica exactamente los valores esperados de ``fx_valuation.json``,
``portfolio_happy_path.json`` y ``coverage_cases.json``.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

from src.investments.domain.entities import FxObservation, PriceObservation
from src.investments.domain.enums import CoverageStatus, PriceKind, ValuationState
from src.investments.domain.position import Position
from src.investments.domain.projection import proyectar_operaciones
from src.investments.domain.valuation import valorar_cartera, valorar_instrumento
from src.investments.domain.values import AccountId, InstrumentId, Quantity

from .helpers_fixtures import (
    RECIBIDO_EN,
    cargar_fixture,
    construir_operaciones_happy_path,
)

_UTC = timezone.utc


def _posicion(instrument_id: str, cantidad: str) -> Position:
    return Position(
        investment_account_id=AccountId("inv_account_demo_01"),
        instrument_id=InstrumentId(instrument_id),
        quantity=Quantity(Decimal(cantidad)),
    )


def _precio(
    instrument_id: str,
    fecha: date,
    precio: str,
    moneda: str = "EUR",
    kind: PriceKind = PriceKind.NAV,
) -> PriceObservation:
    return PriceObservation(
        instrument_id=InstrumentId(instrument_id),
        effective_date=fecha,
        price=Decimal(precio),
        currency=moneda,
        kind=kind,
        provider="synthetic_market_provider",
        received_at=RECIBIDO_EN,
    )


def _fx(base: str, quote: str, tasa: str, fecha: date) -> FxObservation:
    return FxObservation(
        base_currency=base,
        quote_currency=quote,
        rate=Decimal(tasa),
        effective_date=fecha,
        provider="synthetic_fx_provider",
        received_at=RECIBIDO_EN,
    )


class TestValoracionConFx:
    def test_fixture_fx_valuation_reproducible(self) -> None:
        """AC-INV-005: 10 × 50 USD × 0,92 = 460.00 EUR, nativo 500.00 USD."""
        data = cargar_fixture("fx_valuation.json")
        instrumento = data["instrument"]["instrument_id"]
        fecha = date.fromisoformat(data["fx"]["effective_date"])
        posicion = _posicion(instrumento, data["position"]["quantity"])
        precios = [
            _precio(
                instrumento,
                fecha,
                data["position"]["price"],
                moneda=data["position"]["native_currency"],
                kind=PriceKind.CLOSE,
            )
        ]
        fxs = [_fx("USD", "EUR", data["fx"]["rate"], fecha)]

        valoracion = valorar_instrumento(posicion, precios, fxs, fecha)

        esperado = data["expected"]
        assert valoracion.native_value is not None
        assert valoracion.native_value.amount == Decimal(esperado["native_value_usd"])
        assert valoracion.native_value.currency == "USD"
        assert valoracion.value_base is not None
        assert valoracion.value_base.amount == Decimal(esperado["value_eur"])
        assert valoracion.value_base.currency == "EUR"
        # Se conserva el FX aplicado con fecha efectiva y procedencia.
        assert valoracion.fx_applied is not None
        assert valoracion.fx_applied.rate == Decimal(data["fx"]["rate"])
        assert valoracion.fx_applied.pair == data["fx"]["pair"]
        assert valoracion.fx_applied.effective_date == fecha
        assert valoracion.fx_applied.source == "synthetic_fx_provider"
        assert valoracion.state is ValuationState.FRESH


class TestValoracionHappyPath:
    def test_valor_instrumento_y_cartera_exactos(self) -> None:
        """Fixture happy path: 9 × 105.00 = 945.00; cartera = 945 + 368 = 1313.00."""
        data = cargar_fixture("portfolio_happy_path.json")
        proyeccion = proyectar_operaciones(construir_operaciones_happy_path(data))
        cierre = data["closing_price"]
        fecha = date.fromisoformat(cierre["effective_date"])
        precios = [
            _precio(
                data["instrument"]["instrument_id"],
                fecha,
                cierre["price"],
                moneda=cierre["currency"],
                kind=PriceKind(cierre["kind"]),
            )
        ]

        cartera = valorar_cartera(proyeccion, precios, [], fecha)

        esperado = data["expected"]
        componente = cartera.instruments[0]
        assert componente.value_base is not None
        assert componente.value_base.amount == Decimal(esperado["instrument_value_eur"])
        assert cartera.status is CoverageStatus.COMPLETE
        assert cartera.total is not None
        assert cartera.total.amount == Decimal(esperado["portfolio_value_eur"])
        assert cartera.total.currency == "EUR"


class TestArrastreFinDeSemana:
    def test_fin_de_semana_conserva_fecha_del_viernes(self) -> None:
        """AC-INV-006/007 (coverage_cases): el precio arrastrado conserva su
        fecha efectiva real (2026-02-06) y se marca carried_forward."""
        data = cargar_fixture("coverage_cases.json")["weekend_carry_forward"]
        fecha_precio = date.fromisoformat(data["last_price_date"])
        esperada = date.fromisoformat(data["expected_price_effective_date"])
        posicion = _posicion("instrument_demo_fund_01", "9.000000")
        precios = [_precio("instrument_demo_fund_01", fecha_precio, "105.00")]

        for dia in data["valuation_dates"]:
            valoracion = valorar_instrumento(
                posicion, precios, [], date.fromisoformat(dia)
            )
            assert valoracion.state is ValuationState.CARRIED_FORWARD
            assert valoracion.price_effective_date == esperada
            # "complete_carried_forward": el componente sigue siendo calculable.
            assert valoracion.value_base is not None

    def test_dia_con_precio_publicado_es_fresh(self) -> None:
        posicion = _posicion("instrument_demo_fund_01", "9.000000")
        precios = [_precio("instrument_demo_fund_01", date(2026, 2, 6), "105.00")]
        valoracion = valorar_instrumento(posicion, precios, [], date(2026, 2, 6))
        assert valoracion.state is ValuationState.FRESH


class TestPrecioAusente:
    def test_precio_ausente_no_es_cero(self) -> None:
        """coverage_cases.missing_price: componente None y total parcial."""
        data = cargar_fixture("coverage_cases.json")["missing_price"]
        assert data["quantity_known"] is True and data["price_known"] is False
        posicion = _posicion(data["instrument_id"], "5.000000")

        valoracion = valorar_instrumento(posicion, [], [], date(2026, 2, 6))
        assert valoracion.state is ValuationState.MISSING
        assert valoracion.value_base is None  # nunca cero
        assert valoracion.native_value is None
        assert valoracion.reason is not None
        # La cantidad se conserva aunque el precio falte.
        assert valoracion.quantity == Decimal("5.000000")

    def test_cartera_con_precio_ausente_queda_parcial(self) -> None:
        data = cargar_fixture("coverage_cases.json")["missing_price"]
        happy = cargar_fixture("portfolio_happy_path.json")
        proyeccion = proyectar_operaciones(construir_operaciones_happy_path(happy))
        # Sin observaciones de precio: el único instrumento queda sin valorar.
        cartera = valorar_cartera(proyeccion, [], [], date(2026, 2, 6))
        assert cartera.status.value == data["expected_portfolio_state"]
        assert cartera.total is None  # el total parcial no se presenta como total
        assert len(cartera.missing_components) == 1

    def test_efectivo_no_eur_sin_fx_tambien_es_parcial(self) -> None:
        from src.investments.domain.position import CashBalance
        from src.investments.domain.projection import ProjectionResult
        from src.investments.domain.values import Money

        proyeccion = ProjectionResult(
            positions={},
            cash={"USD": CashBalance(balance=Money(Decimal("100.00"), "USD"))},
        )
        cartera = valorar_cartera(proyeccion, [], [], date(2026, 2, 6))
        assert cartera.status is CoverageStatus.PARTIAL
        assert cartera.total is None
        assert "efectivo:USD" in cartera.missing_components
