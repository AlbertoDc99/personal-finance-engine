"""Tests de entidades: identidad de instrumentos, patas e invariantes."""

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from src.investments.domain.entities import (
    InvestmentOperation,
    Instrument,
    OperationLeg,
    ReconciliationIncident,
    SourceEvidence,
    validar_reconciliacion_de_patas,
)
from src.investments.domain.enums import (
    InstrumentKind,
    OperationKind,
    OperationStatus,
)
from src.investments.domain.errors import (
    OperacionInvalidaError,
    PatasNoReconcilianError,
)
from src.investments.domain.values import (
    AccountId,
    BookId,
    EvidenceId,
    IncidentId,
    InstrumentId,
    Money,
    OperationId,
    OwnerId,
    Quantity,
)

_UTC = timezone.utc


def _instrumento(**kwargs) -> Instrument:
    valores = {
        "instrument_id": InstrumentId("inst_a"),
        "instrument_kind": InstrumentKind.FUND,
        "name_display": "Fondo Índice Sintético Global",
        "currency": "EUR",
    }
    valores.update(kwargs)
    return Instrument(**valores)


class TestIdentidadDeInstrumento:
    def test_mismo_nombre_distinto_id_no_fusiona(self) -> None:
        """AC-INV-012: un instrumento con nombre igual pero identificador
        distinto no se fusiona."""
        a = _instrumento(instrument_id=InstrumentId("inst_a"), isin="ES0000000001")
        b = _instrumento(instrument_id=InstrumentId("inst_b"), isin="ES0000000002")
        assert a.name_display == b.name_display
        assert a.same_identity(b) is False

    def test_mismo_isin_distinto_nombre_es_identidad(self) -> None:
        a = _instrumento(isin="ES0000000001", name_display="Nombre A")
        b = _instrumento(
            instrument_id=InstrumentId("inst_b"),
            isin="ES0000000001",
            name_display="Nombre B",
        )
        assert a.same_identity(b) is True

    def test_ticker_mas_mic_es_identidad(self) -> None:
        a = _instrumento(ticker="SYNTH", mic="XNAS")
        b = _instrumento(instrument_id=InstrumentId("inst_b"), ticker="SYNTH", mic="XNAS")
        assert a.same_identity(b) is True

    def test_ticker_sin_mic_no_basta(self) -> None:
        a = _instrumento(ticker="SYNTH")
        b = _instrumento(instrument_id=InstrumentId("inst_b"), ticker="SYNTH")
        assert a.same_identity(b) is False

    def test_solo_nombre_nunca_es_identidad(self) -> None:
        a = _instrumento()
        b = _instrumento(instrument_id=InstrumentId("inst_b"))
        assert a.same_identity(b) is False


class TestPatas:
    def test_pata_vacia_prohibida(self) -> None:
        with pytest.raises(OperacionInvalidaError):
            OperationLeg()

    def test_cantidad_sin_instrumento_prohibida(self) -> None:
        with pytest.raises(OperacionInvalidaError):
            OperationLeg(quantity=Quantity(Decimal("1")))

    def test_patas_reconcilian_con_total_declarado(self) -> None:
        patas = (
            OperationLeg(
                cash=Money(Decimal("-900.00"), "EUR"),
                quantity=Quantity(Decimal("9.000000")),
                instrument_id=InstrumentId("inst_a"),
            ),
            OperationLeg(fee=Money(Decimal("-2.00"), "EUR")),
        )
        # No debe lanzar: -900.00 + -2.00 == -902.00
        validar_reconciliacion_de_patas(
            patas, Money(Decimal("-902.00"), "EUR"), Decimal("0.01")
        )

    def test_patas_que_no_reconcilian_lanzan_error(self) -> None:
        patas = (
            OperationLeg(cash=Money(Decimal("-900.00"), "EUR")),
            OperationLeg(fee=Money(Decimal("-2.00"), "EUR")),
        )
        with pytest.raises(PatasNoReconcilianError):
            validar_reconciliacion_de_patas(
                patas, Money(Decimal("-950.00"), "EUR"), Decimal("0.01")
            )

    def test_operacion_valida_patas_contra_total_declarado(self) -> None:
        with pytest.raises(PatasNoReconcilianError):
            InvestmentOperation(
                operation_id=OperationId("op_x"),
                owner_id=OwnerId("owner_demo_01"),
                investment_account_id=AccountId("inv_account_demo_01"),
                book_id=BookId("portfolio"),
                kind=OperationKind.BUY,
                effective_date=date(2026, 1, 3),
                status=OperationStatus.BOOKED,
                legs=(OperationLeg(cash=Money(Decimal("-900.00"), "EUR")),),
                declared_cash_total=Money(Decimal("-902.00"), "EUR"),
            )


class TestFechasYTimestamps:
    def test_fecha_de_negocio_no_admite_datetime(self) -> None:
        with pytest.raises(OperacionInvalidaError):
            InvestmentOperation(
                operation_id=OperationId("op_x"),
                owner_id=OwnerId("o"),
                investment_account_id=AccountId("a"),
                book_id=BookId("portfolio"),
                kind=OperationKind.FEE,
                effective_date=datetime(2026, 1, 3, tzinfo=_UTC),  # type: ignore[arg-type]
                status=OperationStatus.BOOKED,
                legs=(OperationLeg(cash=Money(Decimal("-1"), "EUR")),),
            )

    def test_evidencia_exige_timestamp_con_zona(self) -> None:
        with pytest.raises(OperacionInvalidaError):
            SourceEvidence(
                evidence_id=EvidenceId("ev_1"),
                provider="synthetic_provider",
                account_fingerprint=None,
                interval_start=date(2026, 1, 1),
                interval_end=date(2026, 1, 31),
                received_at=datetime(2026, 2, 1, 12, 0),  # sin zona horaria
                payload_hash="abc123",
                adapter_version="0.1.0",
                validation_result="ok",
            )


class TestIncidenteDeConciliacion:
    def test_nunca_reemplaza_release_verificada(self) -> None:
        with pytest.raises(OperacionInvalidaError):
            ReconciliationIncident(
                incident_id=IncidentId("inc_1"),
                investment_account_id=AccountId("a"),
                instrument_id=InstrumentId("i"),
                derived_quantity=Quantity(Decimal("100")),
                snapshot_quantity=Quantity(Decimal("99")),
                difference=Quantity(Decimal("1")),
                detected_at=datetime(2026, 2, 10, tzinfo=_UTC),
                motivo="prueba",
                replace_verified_release=True,
            )
