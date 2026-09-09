"""Catálogos controlados del dominio de inversiones (spec `investments.md`)."""

from __future__ import annotations

from enum import Enum


class InstrumentKind(str, Enum):
    """Tipo de instrumento (spec §5). ``derivative`` queda reservado para la
    futura extensión de trading; no forma parte de la primera implementación."""

    FUND = "fund"
    MONEY_MARKET_FUND = "money_market_fund"
    EQUITY = "equity"
    ETF = "etf"
    CASH = "cash"
    DERIVATIVE = "derivative"  # reservado; sin implementación en fase 1
    UNKNOWN = "unknown"  # exportación sin clasificación estructural fiable


class OperationKind(str, Enum):
    """Catálogo completo de tipos de operación (spec §6.2)."""

    EXTERNAL_DEPOSIT = "external_deposit"
    EXTERNAL_WITHDRAWAL = "external_withdrawal"
    BUY = "buy"
    SELL = "sell"
    FUND_SWITCH_OUT = "fund_switch_out"
    FUND_SWITCH_IN = "fund_switch_in"
    DIVIDEND = "dividend"
    INTEREST = "interest"
    OTHER_INCOME = "other_income"
    FEE = "fee"
    TAX = "tax"
    INTERNAL_CASH_TRANSFER = "internal_cash_transfer"
    FX_EXCHANGE = "fx_exchange"
    SPLIT = "split"
    MERGER = "merger"
    MANUAL_ADJUSTMENT = "manual_adjustment"  # solo con decisión y auditoría explícitas
    UNCLASSIFIED_CASH = "unclassified_cash"  # evidencia de caja sin semántica demostrable


class OperationStatus(str, Enum):
    """Estado de una operación versionada (spec §6.2)."""

    BOOKED = "booked"
    PENDING = "pending"
    CANCELLED = "cancelled"
    CORRECTED = "corrected"


class BookKind(str, Enum):
    """Libro de inversión (spec §4.2)."""

    PORTFOLIO = "portfolio"
    TRADING = "trading"


class AccountStatus(str, Enum):
    """Estado de una cuenta de inversión (spec §4.1)."""

    ACTIVE = "active"
    CLOSED = "closed"
    DISCONNECTED = "disconnected"


class InstrumentStatus(str, Enum):
    """Estado de un instrumento (spec §5)."""

    ACTIVE = "active"
    MATURED = "matured"
    DELISTED = "delisted"
    UNKNOWN = "unknown"


class CoverageStatus(str, Enum):
    """Cobertura de datos: nunca se disfraza una ausencia como completa."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    UNKNOWN = "unknown"


class PriceKind(str, Enum):
    """Tipo de observación de precio (spec §8.1)."""

    CLOSE = "close"
    NAV = "nav"
    OTHER = "other"


class ValuationState(str, Enum):
    """Estado de un componente de valoración diaria.

    - ``fresh``: precio publicado con fecha efectiva igual al día valorado.
    - ``carried_forward``: se arrastra el último precio conocido conservando
      su fecha efectiva real (fines de semana, festivos, retrasos de NAV).
    - ``missing``: no existe precio aplicable; el componente NO es calculable
      y NUNCA se sustituye por cero.
    """

    FRESH = "fresh"
    CARRIED_FORWARD = "carried_forward"
    MISSING = "missing"
