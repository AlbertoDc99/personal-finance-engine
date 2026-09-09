from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from src.investments.domain.entities import PriceObservation
from src.investments.domain.enums import PriceKind
from src.investments.domain.valuation import (
    construir_indice_valoracion,
    precio_efectivo,
)
from src.investments.domain.values import InstrumentId


def test_indice_temporal_conserva_la_regla_de_ultima_revision_aplicable() -> None:
    instrument = InstrumentId("instrument_test")
    observations = (
        PriceObservation(
            instrument_id=instrument,
            effective_date=date(2026, 1, 2),
            price=Decimal("10"),
            currency="EUR",
            kind=PriceKind.CLOSE,
            provider="test",
            received_at=datetime(2026, 1, 2, 18, tzinfo=timezone.utc),
        ),
        PriceObservation(
            instrument_id=instrument,
            effective_date=date(2026, 1, 2),
            price=Decimal("11"),
            currency="EUR",
            kind=PriceKind.CLOSE,
            provider="test",
            received_at=datetime(2026, 1, 2, 19, tzinfo=timezone.utc),
        ),
        PriceObservation(
            instrument_id=instrument,
            effective_date=date(2026, 1, 5),
            price=Decimal("12"),
            currency="EUR",
            kind=PriceKind.CLOSE,
            provider="test",
            received_at=datetime(2026, 1, 5, 18, tzinfo=timezone.utc),
        ),
    )
    index = construir_indice_valoracion(observations, ())

    for day in (date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 4), date(2026, 1, 5)):
        assert precio_efectivo(observations, instrument, day) == precio_efectivo(
            observations, instrument, day, indice=index
        )

    selected = precio_efectivo(observations, instrument, date(2026, 1, 2), indice=index)
    assert selected is not None
    assert selected.price == Decimal("11")
