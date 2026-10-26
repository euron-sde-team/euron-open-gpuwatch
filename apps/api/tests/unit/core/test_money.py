from decimal import Decimal

from gpuwatch.core.money import NUSD_PER_USD, nusd_to_usd, usd_to_nusd
from gpuwatch.costs.rates import seconds_cost


def test_usd_round_trip() -> None:
    assert usd_to_nusd("1") == NUSD_PER_USD
    assert usd_to_nusd(Decimal("0.000000001")) == 1
    assert nusd_to_usd(2_500_000_000) == 2.5


def test_usd_to_nusd_rounds_up() -> None:
    assert usd_to_nusd("0.0000000001") == 1


def test_seconds_cost_rounds_to_the_nearest_nano_dollar() -> None:
    assert seconds_cost(3600, 2_000_000_000) == 2_000_000_000
    assert seconds_cost(1, 1_000_000_000) == 277_778  # 277777.7... rounds up
    assert seconds_cost(0, 5_000_000_000) == 0
