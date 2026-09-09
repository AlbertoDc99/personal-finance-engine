from datetime import date
from decimal import Decimal
import pytest
from src.investments.domain.errors import MonedaIncompatibleError
from src.investments.domain.performance import PuntoDiario, twr_encadenada, xirr
from src.investments.domain.values import Money


@pytest.mark.parametrize('foreign_component', ['valuation', 'first_flow'])
def test_twr_rejects_currency_mismatch_across_the_full_series(foreign_component):
    points = [
        PuntoDiario(date(2026, 1, 1), Money(Decimal('100'), 'USD' if foreign_component == 'valuation' else 'EUR'),
                    Money(Decimal('0'), 'USD' if foreign_component == 'first_flow' else 'EUR')),
        PuntoDiario(date(2026, 1, 2), Money(Decimal('100'), 'EUR'), Money(Decimal('0'), 'EUR')),
    ]
    with pytest.raises(MonedaIncompatibleError):
        twr_encadenada(points)


def test_same_day_offsetting_flows_have_no_determinate_annual_return():
    result = xirr([(date(2026, 1, 1), Money(Decimal('-100'), 'EUR')),
                   (date(2026, 1, 1), Money(Decimal('100'), 'EUR'))])
    assert result.value is None
    assert result.coverage.value == 'unknown'
