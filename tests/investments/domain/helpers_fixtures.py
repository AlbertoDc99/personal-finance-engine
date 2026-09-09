"""Utilidades de tests: carga de fixtures sintéticos y construcción de entidades.

Los tests solo dependen de rutas dentro de ``deliverable/``. Los importes se
convierten SIEMPRE a ``Decimal`` desde las cadenas del JSON: nunca float.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.investments.domain.entities import InvestmentOperation, OperationLeg
from src.investments.domain.enums import OperationKind, OperationStatus
from src.investments.domain.values import (
    AccountId,
    BookId,
    InstrumentId,
    Money,
    OperationId,
    OwnerId,
    Quantity,
)

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"

# Timestamp de recepción sintético y determinista (con zona UTC).
RECIBIDO_EN = datetime(2026, 2, 10, 12, 0, 0, tzinfo=timezone.utc)


def cargar_fixture(nombre: str) -> dict[str, Any]:
    """Carga un fixture JSON desde ``deliverable/tests/fixtures``."""
    ruta = FIXTURES_DIR / nombre
    return json.loads(ruta.read_text(encoding="utf-8"))


def construir_operacion(
    op: dict[str, Any],
    owner_id: str,
    account_id: str,
    book_id: str,
    instrument_id: str | None,
) -> InvestmentOperation:
    """Convierte un diccionario de operación del fixture en la entidad."""
    componentes: dict[str, Any] = {}
    if op.get("cash_eur") is not None:
        componentes["cash"] = Money(Decimal(op["cash_eur"]), "EUR")
    if op.get("instrument_quantity") is not None:
        componentes["quantity"] = Quantity(Decimal(op["instrument_quantity"]))
        componentes["instrument_id"] = InstrumentId(instrument_id or "")
    pata = OperationLeg(**componentes)
    return InvestmentOperation(
        operation_id=OperationId(op["operation_id"]),
        owner_id=OwnerId(owner_id),
        investment_account_id=AccountId(account_id),
        book_id=BookId(book_id),
        kind=OperationKind(op["kind"]),
        effective_date=date.fromisoformat(op["effective_date"]),
        status=OperationStatus(op["status"]),
        legs=(pata,),
    )


def construir_operaciones_happy_path(data: dict[str, Any]) -> list[InvestmentOperation]:
    """Construye las operaciones del fixture ``portfolio_happy_path.json``."""
    return [
        construir_operacion(
            op,
            owner_id=data["owner_id"],
            account_id=data["account"]["investment_account_id"],
            book_id=data["account"]["book"],
            instrument_id=data["instrument"]["instrument_id"],
        )
        for op in data["operations"]
    ]
