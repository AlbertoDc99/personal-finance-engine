"""Tests de los objetos de valor: Decimal obligatorio y monedas seguras."""

from datetime import date
from decimal import Decimal

import pytest

from src.investments.domain.errors import MonedaIncompatibleError, ValorInvalidoError
from src.investments.domain.values import FxRate, Money, Quantity


class TestMoney:
    def test_suma_misma_moneda(self) -> None:
        resultado = Money(Decimal("10.50"), "EUR") + Money(Decimal("2.25"), "EUR")
        assert resultado == Money(Decimal("12.75"), "EUR")

    def test_resta_y_negacion(self) -> None:
        assert Money(Decimal("10"), "EUR") - Money(Decimal("4"), "EUR") == Money(
            Decimal("6"), "EUR"
        )
        assert -Money(Decimal("5"), "EUR") == Money(Decimal("-5"), "EUR")

    def test_monedas_distintas_lanza_error(self) -> None:
        with pytest.raises(MonedaIncompatibleError):
            Money(Decimal("1"), "EUR") + Money(Decimal("1"), "USD")

    def test_float_prohibido(self) -> None:
        with pytest.raises(ValorInvalidoError):
            Money(1.5, "EUR")  # type: ignore[arg-type]

    def test_moneda_invalida(self) -> None:
        with pytest.raises(ValorInvalidoError):
            Money(Decimal("1"), "eur")
        with pytest.raises(ValorInvalidoError):
            Money(Decimal("1"), "EURO")

    def test_multiplicar_por_decimal(self) -> None:
        assert Money(Decimal("105.00"), "EUR").multiplicar(Decimal("9")) == Money(
            Decimal("945.00"), "EUR"
        )

    def test_multiplicar_por_float_prohibido(self) -> None:
        with pytest.raises(ValorInvalidoError):
            Money(Decimal("1"), "EUR").multiplicar(2.0)  # type: ignore[arg-type]


class TestQuantity:
    def test_suma_firmada(self) -> None:
        assert Quantity(Decimal("9.000000")) + Quantity(Decimal("-2")) == Quantity(
            Decimal("7.000000")
        )

    def test_float_prohibido(self) -> None:
        with pytest.raises(ValorInvalidoError):
            Quantity(9.0)  # type: ignore[arg-type]


class TestFxRate:
    def test_convierte_conservando_procedencia(self) -> None:
        fx = FxRate(
            base_currency="USD",
            quote_currency="EUR",
            rate=Decimal("0.92"),
            effective_date=date(2026, 2, 6),
            source="synthetic_fx_provider",
        )
        convertido = fx.convertir(Money(Decimal("500.00"), "USD"))
        assert convertido == Money(Decimal("460.0000"), "EUR")
        assert fx.pair == "USD/EUR"
        assert fx.effective_date == date(2026, 2, 6)

    def test_moneda_incompatible(self) -> None:
        fx = FxRate("USD", "EUR", Decimal("0.92"), date(2026, 2, 6), "sintetico")
        with pytest.raises(MonedaIncompatibleError):
            fx.convertir(Money(Decimal("1"), "GBP"))

    def test_tasa_no_positiva_prohibida(self) -> None:
        with pytest.raises(ValorInvalidoError):
            FxRate("USD", "EUR", Decimal("0"), date(2026, 2, 6), "sintetico")

    def test_tasa_float_prohibida(self) -> None:
        with pytest.raises(ValorInvalidoError):
            FxRate("USD", "EUR", 0.92, date(2026, 2, 6), "sintetico")  # type: ignore[arg-type]
