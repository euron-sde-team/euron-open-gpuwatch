"""Money helpers. All amounts are integer nano-dollars (nUSD); 1 USD = 1e9 nUSD."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal

NUSD_PER_USD = 1_000_000_000


def usd_to_nusd(usd: Decimal | float | str) -> int:
    return int((Decimal(str(usd)) * NUSD_PER_USD).to_integral_value(rounding=ROUND_CEILING))


def nusd_to_usd(nusd: int) -> float:
    return nusd / NUSD_PER_USD
