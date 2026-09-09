"""Entidades del dominio de inversiones (spec `investments.md` §4–§8).

Todas las entidades son dataclasses congeladas (inmutables). Las correcciones
no mutan la historia: se crea una nueva revisión que referencia a la anterior
mediante ``supersedes_operation_id``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Sequence

from src.investments.domain.enums import (
    AccountStatus,
    BookKind,
    InstrumentKind,
    InstrumentStatus,
    OperationKind,
    OperationStatus,
    PriceKind,
)
from src.investments.domain.errors import (
    OperacionInvalidaError,
    PatasNoReconcilianError,
    ValorInvalidoError,
)
from src.investments.domain.values import (
    AccountId,
    BookId,
    EvidenceId,
    FxRate,
    IncidentId,
    InstrumentId,
    Money,
    OperationId,
    OwnerId,
    Quantity,
)


def _validar_fecha_negocio(valor: object, contexto: str) -> None:
    """Una fecha de negocio es ``date`` puro; nunca ``datetime``."""
    if isinstance(valor, datetime) or not isinstance(valor, date):
        raise OperacionInvalidaError(
            f"{contexto} debe ser una fecha de negocio (date), "
            f"no {type(valor).__name__}."
        )


def _validar_timestamp_utc(valor: object, contexto: str) -> None:
    """Un timestamp de recepción es ``datetime`` con zona horaria (UTC)."""
    if not isinstance(valor, datetime) or valor.tzinfo is None:
        raise OperacionInvalidaError(
            f"{contexto} debe ser un datetime con zona horaria UTC."
        )


@dataclass(frozen=True, slots=True)
class InvestmentAccount:
    """Cuenta del titular en un bróker o banco de inversión (spec §4.1).

    ``provider_account_fingerprint`` es una huella; nunca un identificador
    sensible que pueda aparecer en rutas o logs.
    """

    investment_account_id: AccountId
    owner_id: OwnerId
    provider: str
    base_currency: str
    status: AccountStatus
    valid_from: date
    provider_account_fingerprint: str | None = None
    valid_to: date | None = None

    def __post_init__(self) -> None:
        _validar_fecha_negocio(self.valid_from, "InvestmentAccount.valid_from")
        if self.valid_to is not None:
            _validar_fecha_negocio(self.valid_to, "InvestmentAccount.valid_to")


@dataclass(frozen=True, slots=True)
class InvestmentBook:
    """Libro de inversión dentro de una cuenta (spec §4.2).

    ``portfolio`` y ``trading`` se mantienen separados; la consolidación es
    opcional en presentación, nunca una fusión de hechos.
    """

    book_id: BookId
    investment_account_id: AccountId
    kind: BookKind


@dataclass(frozen=True, slots=True)
class Instrument:
    """Activo económico, no una posición concreta (spec §5).

    La equivalencia entre fuentes exige ISIN o la pareja ticker+MIC.
    El nombre de presentación NO es identidad suficiente.
    """

    instrument_id: InstrumentId
    instrument_kind: InstrumentKind
    name_display: str
    currency: str
    isin: str | None = None
    ticker: str | None = None
    mic: str | None = None
    status: InstrumentStatus = InstrumentStatus.ACTIVE
    provider_instrument_key: str | None = None

    def same_identity(self, otro: "Instrument") -> bool:
        """Decide si dos instrumentos son el mismo activo económico.

        Reglas (spec §5):
        - Si ambos tienen ISIN, la identidad la decide el ISIN.
        - Si ambos tienen pareja ticker+MIC completa, la decide esa pareja.
        - En cualquier otro caso NO hay evidencia suficiente: se devuelve
          ``False``. El nombre nunca participa en la decisión.
        """
        if self.isin is not None and otro.isin is not None:
            return self.isin == otro.isin
        if (
            self.ticker is not None
            and self.mic is not None
            and otro.ticker is not None
            and otro.mic is not None
        ):
            return (self.ticker, self.mic) == (otro.ticker, otro.mic)
        return False


@dataclass(frozen=True, slots=True)
class SourceEvidence:
    """Evidencia inmutable de origen (spec §6.1).

    Los payloads completos permanecen privados y nunca entran en Git o logs;
    aquí solo se conserva el hash, las fechas y la versión del adaptador.
    """

    evidence_id: EvidenceId
    provider: str
    account_fingerprint: str | None
    interval_start: date | None
    interval_end: date | None
    received_at: datetime
    payload_hash: str
    adapter_version: str
    validation_result: str

    def __post_init__(self) -> None:
        _validar_timestamp_utc(self.received_at, "SourceEvidence.received_at")
        if self.interval_start is not None:
            _validar_fecha_negocio(self.interval_start, "SourceEvidence.interval_start")
        if self.interval_end is not None:
            _validar_fecha_negocio(self.interval_end, "SourceEvidence.interval_end")


@dataclass(frozen=True, slots=True)
class OperationLeg:
    """Pata de una operación (spec §6.3).

    Componentes opcionales pero al menos uno presente:
    - ``cash``: efectivo firmado en su moneda;
    - ``quantity``: cantidad firmada de instrumento (exige ``instrument_id``);
    - ``fee``: comisión (firmada, normalmente negativa);
    - ``tax``: impuesto (firmado, normalmente negativo);
    - ``fx``: tipo de cambio o contrapartida aplicada.
    """

    cash: Money | None = None
    quantity: Quantity | None = None
    instrument_id: InstrumentId | None = None
    fee: Money | None = None
    tax: Money | None = None
    fx: FxRate | None = None
    documented_cost: Money | None = None

    def __post_init__(self) -> None:
        if (
            self.cash is None
            and self.quantity is None
            and self.fee is None
            and self.tax is None
            and self.fx is None
            and self.documented_cost is None
        ):
            raise OperacionInvalidaError(
                "Una pata de operación debe contener al menos un componente."
            )
        if self.quantity is not None and self.instrument_id is None:
            raise OperacionInvalidaError(
                "Una pata con cantidad de instrumento exige instrument_id."
            )
        if self.documented_cost is not None and (
            self.quantity is None or self.instrument_id is None
        ):
            raise OperacionInvalidaError(
                "Un coste documentado exige cantidad e instrumento en la misma pata."
            )


def validar_reconciliacion_de_patas(
    legs: Sequence[OperationLeg],
    total_declarado: Money,
    tolerancia: Decimal,
) -> None:
    """Comprueba que las patas reconcilian con el total declarado por la fuente.

    Suma los componentes de efectivo (``cash``, ``fee``, ``tax``) de las patas
    en la moneda del total declarado y exige que la diferencia absoluta no
    supere la precisión declarada. Si no reconcilia, lanza
    :class:`PatasNoReconcilianError`: nunca se acepta silenciosamente una
    operación incoherente con su fuente.
    """
    if not isinstance(tolerancia, Decimal):
        raise ValorInvalidoError("La tolerancia de reconciliación debe ser Decimal.")
    suma = Decimal("0")
    for pata in legs:
        for componente in (pata.cash, pata.fee, pata.tax):
            if componente is not None and componente.currency == total_declarado.currency:
                suma += componente.amount
    diferencia = abs(suma - total_declarado.amount)
    if diferencia > tolerancia:
        raise PatasNoReconcilianError(
            f"Las patas suman {suma} {total_declarado.currency} pero la fuente "
            f"declara {total_declarado.amount} {total_declarado.currency}; "
            f"diferencia {diferencia} fuera de la precisión declarada "
            f"({tolerancia})."
        )


@dataclass(frozen=True, slots=True)
class InvestmentOperation:
    """Hecho versionado con identidad estable (spec §6.2).

    Una corrección no muta la historia: la nueva revisión referencia a la
    anterior con ``supersedes_operation_id`` y la anterior pasa a estado
    ``corrected``. Si la fuente declara un total de efectivo
    (``declared_cash_total``), las patas deben reconciliar con él dentro de
    ``reconciliation_tolerance``.
    """

    operation_id: OperationId
    owner_id: OwnerId
    investment_account_id: AccountId
    book_id: BookId
    kind: OperationKind
    effective_date: date
    status: OperationStatus
    legs: tuple[OperationLeg, ...] = ()
    trade_at: datetime | None = None
    settled_at: date | None = None
    provider_reference: str | None = None
    source_evidence_id: EvidenceId | None = None
    supersedes_operation_id: OperationId | None = None
    declared_cash_total: Money | None = None
    reconciliation_tolerance: Decimal = Decimal("0.01")

    def __post_init__(self) -> None:
        _validar_fecha_negocio(self.effective_date, "InvestmentOperation.effective_date")
        if self.settled_at is not None:
            _validar_fecha_negocio(self.settled_at, "InvestmentOperation.settled_at")
        if self.trade_at is not None:
            _validar_timestamp_utc(self.trade_at, "InvestmentOperation.trade_at")
        if self.declared_cash_total is not None:
            validar_reconciliacion_de_patas(
                self.legs, self.declared_cash_total, self.reconciliation_tolerance
            )


@dataclass(frozen=True, slots=True)
class PriceObservation:
    """Observación de precio o valor liquidativo (spec §8.1).

    Conserva fecha efectiva de negocio, procedencia y fecha de recepción.
    Un precio posterior puede corregir otro, pero nunca lo sobrescribe sin
    conservar la revisión (por eso las observaciones son inmutables).
    """

    instrument_id: InstrumentId
    effective_date: date
    price: Decimal
    currency: str
    kind: PriceKind
    provider: str
    received_at: datetime
    quality: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.price, Decimal):
            raise ValorInvalidoError(
                "PriceObservation.price debe ser Decimal, nunca float."
            )
        _validar_fecha_negocio(self.effective_date, "PriceObservation.effective_date")
        _validar_timestamp_utc(self.received_at, "PriceObservation.received_at")


@dataclass(frozen=True, slots=True)
class FxObservation:
    """Observación histórica de tipo de cambio (spec §8.1)."""

    base_currency: str
    quote_currency: str
    rate: Decimal
    effective_date: date
    provider: str
    received_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.rate, Decimal):
            raise ValorInvalidoError(
                "FxObservation.rate debe ser Decimal, nunca float."
            )
        _validar_fecha_negocio(self.effective_date, "FxObservation.effective_date")
        _validar_timestamp_utc(self.received_at, "FxObservation.received_at")

    def como_tipo(self) -> FxRate:
        """Convierte la observación en un :class:`FxRate` aplicable,
        conservando fecha efectiva y procedencia."""
        return FxRate(
            base_currency=self.base_currency,
            quote_currency=self.quote_currency,
            rate=self.rate,
            effective_date=self.effective_date,
            source=self.provider,
        )


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """Snapshot de posición informado por el proveedor (spec §7).

    Sirve para corroborar el ledger derivado; nunca lo reemplaza. Si difieren,
    se abre una :class:`ReconciliationIncident`.
    """

    investment_account_id: AccountId
    instrument_id: InstrumentId
    quantity: Quantity
    effective_date: date
    received_at: datetime
    source_evidence_id: EvidenceId | None = None

    def __post_init__(self) -> None:
        _validar_fecha_negocio(self.effective_date, "PositionSnapshot.effective_date")
        _validar_timestamp_utc(self.received_at, "PositionSnapshot.received_at")


@dataclass(frozen=True, slots=True)
class ReconciliationIncident:
    """Incidencia de conciliación entre ledger derivado y snapshot (spec §7).

    Invariante duro: ``replace_verified_release`` es siempre ``False``.
    Un incidente documenta la discrepancia; jamás ajusta la cantidad derivada
    ni reemplaza el último estado verificado.
    """

    incident_id: IncidentId
    investment_account_id: AccountId
    instrument_id: InstrumentId
    derived_quantity: Quantity
    snapshot_quantity: Quantity
    difference: Quantity
    detected_at: datetime
    motivo: str
    replace_verified_release: bool = False

    def __post_init__(self) -> None:
        _validar_timestamp_utc(self.detected_at, "ReconciliationIncident.detected_at")
        if self.replace_verified_release:
            raise OperacionInvalidaError(
                "Un incidente de conciliación nunca reemplaza la release "
                "verificada ni ajusta la cantidad derivada."
            )
