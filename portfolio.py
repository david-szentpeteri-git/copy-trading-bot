"""Portfolio valuation utilities.

Estimates a wallet's total portfolio value from its open Polymarket
positions plus USDC balance, used to calculate proportional trade sizing.
"""

import logging
from typing import Optional

import bullpen

logger = logging.getLogger(__name__)


def estimate_portfolio_value(address: str) -> Optional[float]:
    """Estimate a trader's total portfolio value in USDC.

    Sums the current USDC value of all open positions plus any
    uninvested USDC balance. Returns None if data cannot be fetched.

    Args:
        address: Polymarket proxy wallet address.

    Returns:
        Estimated portfolio value in USDC, or None on error.
    """
    try:
        positions = bullpen.get_positions(address)

        # Log raw structure once so we can see what bullpen actually returns
        if positions:
            logger.debug("get_positions raw sample: %r", positions[0])

        # Guard: skip any entries that aren't dicts (bullpen sometimes returns
        # a flat list of strings instead of objects when positions are sparse)
        position_value = sum(
            float(p.get("current_value", 0) or 0)
            for p in positions
            if isinstance(p, dict)
        )

        return position_value if position_value > 0 else None

    except Exception as exc:
        logger.warning("Could not estimate portfolio for %s: %s", address, exc)
        return None


def get_own_usdc_balance() -> Optional[float]:
    """Fetch the bot's own available USDC balance on Polymarket.

    Returns:
        USDC balance as a float, or None if it cannot be retrieved.
    """
    try:
        balances = bullpen.get_own_balances()

        # Bullpen returns {"chains": [...], "total_usd": ...}
        # Find the Polymarket chain entry by label
        for entry in balances.get("chains", []):
            if isinstance(entry, dict) and entry.get("label") == "Polymarket":
                return float(entry.get("total_usd", 0))

        return None

    except Exception as exc:
        logger.warning("Could not fetch own USDC balance: %s", exc)
        return None


def calculate_trade_size(
    trader_trade_usdc: float,
    trader_portfolio_usdc: float,
    own_portfolio_usdc: float,
    cap_usdc: float,
) -> float:
    """Calculate how much USDC to invest in a copied trade.

    Applies the same portfolio percentage the tracked trader used,
    then caps it at the configured maximum.

    Args:
        trader_trade_usdc: How much USDC the tracked trader spent.
        trader_portfolio_usdc: The tracked trader's estimated total portfolio.
        own_portfolio_usdc: Our own available USDC balance.
        cap_usdc: Hard maximum USDC per trade.

    Returns:
        USDC amount to bet, rounded to 2 decimal places.

    Example:
        >>> calculate_trade_size(1000, 10000, 500, 10)
        10.0  # 10% of $500 = $50, but capped at $10
    """
    # What fraction of their portfolio did the trader use?
    trade_pct = trader_trade_usdc / trader_portfolio_usdc

    # Apply the same fraction to our portfolio
    raw_size = own_portfolio_usdc * trade_pct

    # Never exceed the hard cap
    final_size = min(raw_size, cap_usdc)

    return round(final_size, 2)
