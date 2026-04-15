"""Trade executor for the copy trading bot.

Takes a detected trade from a tracked wallet, calculates the
proportional position size, and places the copied order via Bullpen.
"""

import logging
from typing import Dict, Optional

import bullpen
import portfolio
from config import config

logger = logging.getLogger(__name__)


def execute_copy_trade(trade: Dict) -> bool:
    """Attempt to copy a single trade from a tracked wallet.

    Fetches both the tracked trader's portfolio and our own balance,
    calculates the proportional USDC size (capped at config.trade_cap_usdc),
    then places a market buy order for the same outcome.

    Args:
        trade: Trade dict from the monitor, must contain:
               - trader_address (str)
               - condition_id (str)
               - outcome (str)
               - usdc_size (float)
               - title (str)

    Returns:
        True if the order was placed successfully, False otherwise.
    """
    trader_address = trade["trader_address"]
    condition_id = trade["condition_id"]
    outcome = trade["outcome"]
    trader_usdc_spent = float(trade["usdc_size"])
    market_title = trade.get("title", condition_id)

    # Step 1: Estimate the tracked trader's total portfolio value
    trader_portfolio = portfolio.estimate_portfolio_value(trader_address)
    if not trader_portfolio or trader_portfolio <= 0:
        logger.warning(
            "Could not estimate portfolio for trader %s — skipping trade on '%s'",
            trader_address, market_title,
        )
        return False

    # Step 2: Get our own available USDC balance
    own_balance = portfolio.get_own_usdc_balance()
    if not own_balance or own_balance <= 0:
        logger.warning("Own USDC balance is zero or unavailable — skipping trade on '%s'", market_title)
        return False

    # Step 3: Calculate how much we should bet
    size = portfolio.calculate_trade_size(
        trader_trade_usdc=trader_usdc_spent,
        trader_portfolio_usdc=trader_portfolio,
        own_portfolio_usdc=own_balance,
        cap_usdc=config.trade_cap_usdc,
    )

    # Minimum viable trade size to avoid dust orders
    if size < 0.10:
        logger.info(
            "Calculated size $%.4f is below minimum $0.10 — skipping '%s'",
            size, market_title,
        )
        return False

    logger.info(
        "Copying trade: '%s' → %s | trader spent $%.2f (%.1f%% of $%.2f portfolio) "
        "→ our bet: $%.2f (capped at $%.2f)",
        market_title, outcome,
        trader_usdc_spent,
        (trader_usdc_spent / trader_portfolio) * 100,
        trader_portfolio,
        size,
        config.trade_cap_usdc,
    )

    # Step 4: Place the order via Bullpen CLI
    try:
        result = bullpen.place_buy(condition_id, outcome, size)
        logger.info("Order placed successfully: %s", result)
        return True

    except Exception as exc:
        logger.error("Failed to place order for '%s': %s", market_title, exc)
        return False
