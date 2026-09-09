"""Tests de proyección de posiciones y efectivo desde operaciones booked.

Verifica exactamente los valores esperados de ``portfolio_happy_path.json``
y las reglas de revisión (corrected/superseded), cancelación y pendiente.
"""

from datetime import date
from decimal import Decimal

from src.investments.domain.entities import InvestmentOperation, OperationLeg
from src.investments.domain.enums import OperationKind, OperationStatus
from src.investments.domain.projection import operaciones_vigentes, proyectar_operaciones
from src.investments.domain.values import (
    AccountId,
    BookId,
    InstrumentId,
    Money,
    OperationId,
    OwnerId,
)

from .helpers_fixtures import cargar_fixture, construir_operaciones_happy_path


def _operacion(
    op_id: str,
    cash: str,
    status: OperationStatus = OperationStatus.BOOKED,
    supersedes: str | None = None,
    kind: OperationKind = OperationKind.EXTERNAL_DEPOSIT,
    fecha: date = date(2026, 1, 2),
) -> InvestmentOperation:
    return InvestmentOperation(
        operation_id=OperationId(op_id),
        owner_id=OwnerId("owner_demo_01"),
        investment_account_id=AccountId("inv_account_demo_01"),
        book_id=BookId("portfolio"),
        kind=kind,
        effective_date=fecha,
        status=status,
        legs=(OperationLeg(cash=Money(Decimal(cash), "EUR")),),
        supersedes_operation_id=OperationId(supersedes) if supersedes else None,
    )


class TestHappyPath:
    def test_efectivo_y_cantidad_exactos(self) -> None:
        """Fixture portfolio_happy_path: cash 368.00 y quantity 9.000000."""
        data = cargar_fixture("portfolio_happy_path.json")
        operaciones = construir_operaciones_happy_path(data)
        proyeccion = proyectar_operaciones(operaciones)

        esperado = data["expected"]
        assert proyeccion.efectivo("EUR").amount == Decimal(esperado["cash_eur"])
        instrumento = InstrumentId(data["instrument"]["instrument_id"])
        posicion = proyeccion.positions[instrumento]
        assert posicion.quantity.value == Decimal(esperado["instrument_quantity"])

    def test_sin_coste_documentado_no_hay_pnl(self) -> None:
        """La proyección no inventa coste ni P&L: campos None."""
        data = cargar_fixture("portfolio_happy_path.json")
        proyeccion = proyectar_operaciones(construir_operaciones_happy_path(data))
        posicion = next(iter(proyeccion.positions.values()))
        assert posicion.documented_cost is None
        assert posicion.realized_result is None
        assert posicion.unrealized_result is None


class TestRevisiones:
    def test_correccion_no_duplica(self) -> None:
        """Una operación corrected + su revisión vigente cuentan una sola vez."""
        original = _operacion("op_1", "100.00", status=OperationStatus.CORRECTED)
        revision = _operacion("op_2", "120.00", supersedes="op_1")
        proyeccion = proyectar_operaciones([original, revision])
        assert proyeccion.efectivo("EUR").amount == Decimal("120.00")

    def test_reemplazada_se_excluye_aunque_siga_booked(self) -> None:
        """Si una revisión referencia a otra, la reemplazada no cuenta,
        incluso si su estado no se actualizó todavía."""
        original = _operacion("op_1", "100.00", status=OperationStatus.BOOKED)
        revision = _operacion("op_2", "120.00", supersedes="op_1")
        proyeccion = proyectar_operaciones([original, revision])
        assert proyeccion.efectivo("EUR").amount == Decimal("120.00")

    def test_cancelled_y_pending_no_cuentan(self) -> None:
        operaciones = [
            _operacion("op_1", "100.00"),
            _operacion("op_2", "50.00", status=OperationStatus.CANCELLED),
            _operacion("op_3", "25.00", status=OperationStatus.PENDING),
        ]
        proyeccion = proyectar_operaciones(operaciones)
        assert proyeccion.efectivo("EUR").amount == Decimal("100.00")

    def test_orden_por_fecha_efectiva(self) -> None:
        tardia = _operacion("op_2", "20.00", fecha=date(2026, 2, 1))
        temprana = _operacion("op_1", "10.00", fecha=date(2026, 1, 1))
        vigentes = operaciones_vigentes([tardia, temprana])
        assert [op.operation_id for op in vigentes] == ["op_1", "op_2"]

    def test_filtro_hasta_fecha_de_negocio(self) -> None:
        operaciones = [
            _operacion("op_1", "100.00", fecha=date(2026, 1, 2)),
            _operacion("op_2", "50.00", fecha=date(2026, 2, 1)),
        ]
        proyeccion = proyectar_operaciones(operaciones, hasta=date(2026, 1, 31))
        assert proyeccion.efectivo("EUR").amount == Decimal("100.00")
