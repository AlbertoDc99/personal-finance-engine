from demo import demo


def test_demo_is_deterministic_and_distinguishes_missing_from_zero():
    result = demo()
    assert result == demo()
    full, carried, missing = result['valuations']
    assert full['value_eur'] == '460.00'
    assert carried['state'] == 'carried_forward'
    assert carried['price_effective_date'] == '2026-01-05'
    assert missing['value_eur'] is None
    assert result['period_result_eur'] == '100'
