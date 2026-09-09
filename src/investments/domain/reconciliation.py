"""Conciliación entre ledger derivado y snapshots del proveedor (spec §7).

Un snapshot del proveedor no borra el ledger derivado. Si difieren fuera de
la tolerancia declarada se crea una :class:`ReconciliationIncident` y sigue
visible el último estado verificado: la cantidad derivada NUNCA se ajusta
silenciosamente.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from src.investments.domain.entities import PositionSnapshot, ReconciliationIncident
from src.investments.domain.errors import ValorInvalidoError
from src.investments.domain.position import Position
from src.investments.domain.values import IncidentId, Quantity


def conciliar_posicion(
    derivada: Position,
    snapshot: PositionSnapshot,
    tolerancia: Decimal,
    incident_id: IncidentId,
    detected_at: datetime,
) -> ReconciliationIncident | None:
    """Compara la posición derivada con el snapshot del proveedor.

    - Dentro de la tolerancia declarada: devuelve ``None`` (sin incidencia).
    - Fuera de la tolerancia: devuelve una :class:`ReconciliationIncident`
      con ``replace_verified_release=False``. La función es pura: no muta la
      posición derivada ni el snapshot; documentar la discrepancia es lo
      único que ocurre.

    ``incident_id`` y ``detected_at`` se inyectan para mantener el dominio
    determinista y sin efectos (sin relojes ni generadores globales).
    """
    if not isinstance(tolerancia, Decimal):
        raise ValorInvalidoError("La tolerancia de conciliación debe ser Decimal.")
    if derivada.instrument_id != snapshot.instrument_id:
        raise ValorInvalidoError(
            "La conciliación exige el mismo instrumento en posición y snapshot."
        )
    if derivada.investment_account_id != snapshot.investment_account_id:
        raise ValorInvalidoError(
            "La conciliación exige la misma cuenta en posición y snapshot."
        )

    diferencia = derivada.quantity.value - snapshot.quantity.value
    if abs(diferencia) <= tolerancia:
        return None
    return ReconciliationIncident(
        incident_id=incident_id,
        investment_account_id=derivada.investment_account_id,
        instrument_id=derivada.instrument_id,
        derived_quantity=derivada.quantity,
        snapshot_quantity=snapshot.quantity,
        difference=Quantity(diferencia),
        detected_at=detected_at,
        motivo=(
            f"La cantidad derivada {derivada.quantity.value} difiere del "
            f"snapshot del proveedor {snapshot.quantity.value} en "
            f"{diferencia} (tolerancia {tolerancia}). Se conserva el último "
            "estado verificado sin ajustar la cantidad derivada."
        ),
        replace_verified_release=False,
    )
