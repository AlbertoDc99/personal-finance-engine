"""Offline demonstration using fictitious positions and prices only."""
from datetime import date, datetime, timezone
from decimal import Decimal
import json

from src.investments.domain.entities import FxObservation, PriceObservation
from src.investments.domain.enums import PriceKind
from src.investments.domain.performance import resultado_periodo
from src.investments.domain.position import Position
from src.investments.domain.valuation import valorar_instrumento
from src.investments.domain.values import AccountId, InstrumentId, Money, Quantity


def demo():
    day = date(2026, 1, 5)
    received = datetime(2026, 1, 5, 18, tzinfo=timezone.utc)
    instrument = InstrumentId('synthetic_equity')
    position = Position(AccountId('synthetic_account'), instrument, Quantity(Decimal('10')))
    price = PriceObservation(instrument_id=instrument, effective_date=day,
        price=Decimal('50'), currency='USD', kind=PriceKind.CLOSE,
        provider='synthetic_market', received_at=received)
    fx = FxObservation(base_currency='USD', quote_currency='EUR', rate=Decimal('.92'),
        effective_date=day, provider='synthetic_fx', received_at=received)
    rows = []
    for name, prices, at in [('Complete valuation', [price], day),
                             ('Carried price', [price], date(2026, 1, 6)),
                             ('Missing price', [], day)]:
        value = valorar_instrumento(position, prices, [fx], at)
        rows.append({'scenario': name, 'state': value.state.value,
            'value_eur': None if value.value_base is None else str(value.value_base.amount),
            'price_effective_date': None if value.price_effective_date is None else str(value.price_effective_date)})
    result = resultado_periodo(Money(Decimal('1000'), 'EUR'),
                               Money(Decimal('1300'), 'EUR'), Money(Decimal('200'), 'EUR'))
    return {'data': 'entirely synthetic', 'valuations': rows,
            'period_result_eur': str(result.value.amount)}


if __name__ == '__main__':
    print(json.dumps(demo(), indent=2))
