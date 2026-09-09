"""Objetos de valor tipados del dominio de inversiones.

Reglas duras:

- Nunca se usa ``float`` para dinero ni cantidades: siempre ``Decimal``.
- La aritmética monetaria solo es válida entre importes de la misma moneda.
- Los identificadores son opacos y estables: no se interpreta su contenido.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NewType

from src.investments.domain.errors import MonedaIncompatibleError, ValorInvalidoError

# ---------------------------------------------------------------------------
# Identificadores opacos tipados
# ---------------------------------------------------------------------------
OwnerId = NewType("OwnerId", str)
AccountId = NewType("AccountId", str)
BookId = NewType("BookId", str)
InstrumentId = NewType("InstrumentId", str)
OperationId = NewType("OperationId", str)
EvidenceId = NewType("EvidenceId", str)
ReleaseId = NewType("ReleaseId", str)
IncidentId = NewType("IncidentId", str)


def _validar_decimal(valor: object, contexto: str) -> None:
    """Rechaza cualquier tipo que no sea ``Decimal`` (en particular ``float``)."""
    if not isinstance(valor, Decimal):
        raise ValorInvalidoError(
            f"{contexto} debe ser Decimal, no {type(valor).__name__}: "
            "el dominio prohíbe float para dinero y cantidades."
        )


def _validar_moneda(codigo: object) -> None:
    """Valida un código de moneda ISO 4217 (tres letras mayúsculas)."""
    if not (
        isinstance(codigo, str)
        and len(codigo) == 3
        and codigo.isalpha()
        and codigo.isupper()
    ):
        raise ValorInvalidoError(f"Código de moneda ISO 4217 inválido: {codigo!r}")


@dataclass(frozen=True, slots=True)
class Money:
    """Importe monetario con moneda ISO 4217.

    La aritmética (suma, resta, negación) solo es válida entre importes de la
    misma moneda; mezclar monedas lanza :class:`MonedaIncompatibleError`.
    La conversión entre monedas se hace exclusivamente vía :class:`FxRate`,
    que conserva procedencia y fecha efectiva.
    """

    amount: Decimal
    currency: str

    def __post_init__(self) -> None:
        _validar_decimal(self.amount, "Money.amount")
        _validar_moneda(self.currency)

    @classmethod
    def cero(cls, currency: str) -> "Money":
        """Importe cero en la moneda indicada."""
        return cls(Decimal("0"), currency)

    def _exigir_misma_moneda(self, otro: "Money") -> None:
        if not isinstance(otro, Money):
            raise ValorInvalidoError(
                f"Se esperaba Money, no {type(otro).__name__}."
            )
        if self.currency != otro.currency:
            raise MonedaIncompatibleError(
                f"No se puede operar {self.currency} con {otro.currency}: "
                "la aritmética monetaria exige la misma moneda."
            )

    def __add__(self, otro: "Money") -> "Money":
        self._exigir_misma_moneda(otro)
        return Money(self.amount + otro.amount, self.currency)

    def __sub__(self, otro: "Money") -> "Money":
        self._exigir_misma_moneda(otro)
        return Money(self.amount - otro.amount, self.currency)

    def __neg__(self) -> "Money":
        return Money(-self.amount, self.currency)

    def multiplicar(self, factor: Decimal) -> "Money":
        """Multiplica el importe por un factor ``Decimal`` (p. ej. cantidad)."""
        _validar_decimal(factor, "factor")
        return Money(self.amount * factor, self.currency)

    @property
    def es_cero(self) -> bool:
        """``True`` si el importe es exactamente cero."""
        return self.amount == 0


@dataclass(frozen=True, slots=True)
class Quantity:
    """Cantidad de instrumento (participaciones, títulos), siempre ``Decimal``.

    Puede ser firmada: positiva al comprar/recibir, negativa al vender/entregar.
    """

    value: Decimal

    def __post_init__(self) -> None:
        _validar_decimal(self.value, "Quantity.value")

    def __add__(self, otra: "Quantity") -> "Quantity":
        if not isinstance(otra, Quantity):
            raise ValorInvalidoError(
                f"Se esperaba Quantity, no {type(otra).__name__}."
            )
        return Quantity(self.value + otra.value)

    def __sub__(self, otra: "Quantity") -> "Quantity":
        if not isinstance(otra, Quantity):
            raise ValorInvalidoError(
                f"Se esperaba Quantity, no {type(otra).__name__}."
            )
        return Quantity(self.value - otra.value)

    def __neg__(self) -> "Quantity":
        return Quantity(-self.value)

    @property
    def es_cero(self) -> bool:
        """``True`` si la cantidad es exactamente cero."""
        return self.value == 0


@dataclass(frozen=True, slots=True)
class FxRate:
    """Tipo de cambio aplicable con par, fecha efectiva y procedencia.

    Convierte importes expresados en ``base_currency`` a ``quote_currency``
    multiplicando por ``rate``. Nunca se descarta la procedencia ni la fecha:
    una valoración histórica jamás se reescribe con un tipo actual.
    """

    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_date: date
    source: str

    def __post_init__(self) -> None:
        _validar_moneda(self.base_currency)
        _validar_moneda(self.quote_currency)
        _validar_decimal(self.rate, "FxRate.rate")
        if self.rate <= 0:
            raise ValorInvalidoError(
                f"El tipo de cambio debe ser positivo; recibido {self.rate}."
            )
        if not isinstance(self.effective_date, date):
            raise ValorInvalidoError(
                "FxRate.effective_date debe ser una fecha de negocio (date)."
            )

    @property
    def pair(self) -> str:
        """Par de divisas en formato ``BASE/QUOTE`` (p. ej. ``USD/EUR``)."""
        return f"{self.base_currency}/{self.quote_currency}"

    def convertir(self, importe: Money) -> Money:
        """Convierte un importe de ``base_currency`` a ``quote_currency``."""
        if importe.currency != self.base_currency:
            raise MonedaIncompatibleError(
                f"El tipo {self.pair} no puede convertir un importe en "
                f"{importe.currency}."
            )
        return Money(importe.amount * self.rate, self.quote_currency)
