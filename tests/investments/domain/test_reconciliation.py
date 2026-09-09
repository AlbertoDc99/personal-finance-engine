"""Tests de conciliación: snapshot discrepante crea incidencia sin ajustar.

Verifica exactamente ``coverage_cases.json`` → ``snapshot_discrepancy``:
derivada 100 vs proveedor 99 → incidente, replace=False.
"""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.investments.domain.errors import ValorInvalidoError
from src.investments.domain.entities import PositionSnapshot
from src.investments.domain.position import Position
from src.investments.domain.reconciliation import conciliar_posicion
from src.investments.domain.values import AccountId, IncidentId, InstrumentId, Quantity

from .helpers_fixtures import RECIBIDO_EN, cargar_fixture

_DETECTADO_EN = datetime(2026, 2, 10, 12, 30, 0, tzinfo=timezone.utc)


def _posicion(cantidad: str, instrumento: str = "instrument_demo_fund_01") -> Position:
    return Position(
        investment_account_id=AccountId("inv_account_demo_01"),
        instrument_id=InstrumentId(instrumento),
        quantity=Quantity(Decimal(cantidad)),
    )


def _snapshot(cantidad: str, instrumento: str = "instrument_demo_fund_01") -> PositionSnapshot:
    return PositionSnapshot(
        investment_account_id=AccountId("inv_account_demo_01"),
        instrument_id=InstrumentId(instrumento),
        quantity=Quantity(Decimal(cantidad)),
        effective_date=date(2026, 2, 9),
        received_at=RECIBIDO_EN,
    )


class TestSnapshotDiscrepante:
    def test_fixture_snapshot_discrepancy(self) -> None:
        """AC-INV-008: derivada 100 vs proveedor 99 → incidente, replace=False."""
        data = cargar_fixture("coverage_cases.json")["snapshot_discrepancy"]
        derivada = _posicion(data["derived_quantity"])
        snapshot = _snapshot(data["provider_quantity"])

        incidente = conciliar_posicion(
            derivada,
            snapshot,
            tolerancia=Decimal("0.000001"),
            incident_id=IncidentId("inc_demo_01"),
            detected_at=_DETECTADO_EN,
        )

        assert data["expected_action"] == "open_reconciliation_incident"
        assert incidente is not None
        assert incidente.replace_verified_release is data["replace_verified_release"]
        assert incidente.derived_quantity.value == Decimal(data["derived_quantity"])
        assert incidente.snapshot_quantity.value == Decimal(data["provider_quantity"])
        assert incidente.difference.value == Decimal("1.000000")
        # La cantidad derivada NO se ajusta: sigue siendo la del ledger.
        assert derivada.quantity.value == Decimal(data["derived_quantity"])

    def test_dentro_de_tolerancia_no_hay_incidencia(self) -> None:
        derivada = _posicion("100.000000")
        snapshot = _snapshot("100.000000")
        incidente = conciliar_posicion(
            derivada,
            snapshot,
            tolerancia=Decimal("0.000001"),
            incident_id=IncidentId("inc_demo_02"),
            detected_at=_DETECTADO_EN,
        )
        assert incidente is None

    def test_instrumentos_distintos_no_se_concilian(self) -> None:
        derivada = _posicion("100.000000", instrumento="inst_a")
        snapshot = _snapshot("100.000000", instrumento="inst_b")
        with pytest.raises(ValorInvalidoError):
            conciliar_posicion(
                derivada,
                snapshot,
                tolerancia=Decimal("0.000001"),
                incident_id=IncidentId("inc_demo_03"),
                detected_at=_DETECTADO_EN,
            )
