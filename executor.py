"""Trade executor for the copy trading bot.

Routes each detected trade to either execute_buy() or execute_sell()
based on the trade side. Both functions log every outcome — success,
failure, or skip — to the JSON trade log for dashboard consumption.
"""

import logging
from typing import Dict

import bullpen
import portfolio
import state
import trade_log
from config import config

logger = logging.getLogger(__name__)


def handle_trade(trade: Dict) -> bool:
    """Route a detected trade to the appropriate buy or sell handler.

    Args:
        trade: Trade dict from the monitor. Must contain at minimum:
               trader_address, condition_id, outcome, slug, side,
               usdc_size, size (tokens), title, transaction_hash.

    Returns:
        True if the trade was handled successfully, False otherwise.
    """
    side = trade.get("side", "").upper()

    if side == "BUY":
        return _execute_buy(trade)
    elif side == "SELL":
        return _execute_sell(trade)
    else:
        logger.warning("Unknown trade side '%s' — skipping tx %s", side, trade.get("transaction_hash"))
        return False


def _execute_buy(trade: Dict) -> bool:
    """Copy a BUY trade proportionally and record the position.

    Calculates our stake as the same portfolio % the tracked trader used,
    capped at config.trade_cap_usdc. On success, records the position in
    state so we can mirror their eventual sell.

    Args:
        trade: Trade dict with side == "BUY".

    Returns:
        True if the order was placed successfully, False otherwise.
    """
    trader_address = trade["trader_address"]
    condition_id = trade["condition_id"]
    outcome = trade["outcome"]
    slug = trade["slug"]
    title = trade.get("title", slug)
    trader_usdc_spent = float(trade["usdc_size"])
    their_tx_hash = trade.get("transaction_hash", "")

    # Step 1: Estimate the tracked trader's total portfolio value
    trader_portfolio = portfolio.estimate_portfolio_value(trader_address)
    if not trader_portfolio or trader_portfolio <= 0:
        msg = f"Could not estimate portfolio for trader {trader_address}"
        logger.warning("%s — skipping BUY on '%s'", msg, title)
        trade_log.log_failed("BUY_SKIPPED", trader_address, slug, condition_id, outcome, title, their_tx_hash, msg)
        return False

    # Step 2: Get our own available USDC balance
    own_balance = portfolio.get_own_usdc_balance()
    if not own_balance or own_balance <= 0:
        msg = "Own USDC balance is zero or unavailable"
        logger.warning("%s — skipping BUY on '%s'", msg, title)
        trade_log.log_failed("BUY_SKIPPED", trader_address, slug, condition_id, outcome, title, their_tx_hash, msg)
        return False

    # Step 3: Calculate proportional stake, capped at the hard limit
    size = portfolio.calculate_trade_size(
        trader_trade_usdc=trader_usdc_spent,
        trader_portfolio_usdc=trader_portfolio,
        own_portfolio_usdc=own_balance,
        cap_usdc=config.trade_cap_usdc,
    )
    trade_pct = trader_usdc_spent / trader_portfolio

    # Skip dust orders that would be rejected by the exchange
    if size < 0.10:
        msg = f"Calculated size ${size:.4f} is below minimum $0.10"
        logger.info("%s — skipping BUY on '%s'", msg, title)
        trade_log.log_failed("BUY_SKIPPED", trader_address, slug, condition_id, outcome, title, their_tx_hash, msg)
        return False

    logger.info(
        "BUY '%s' → %s | trader: $%.2f (%.2f%% of $%.0f) → our bet: $%.2f",
        title, outcome, trader_usdc_spent, trade_pct * 100, trader_portfolio, size,
    )

    # Step 4: Place the order and capture the result
    try:
        result = bullpen.place_buy(condition_id, outcome, size)

        # Extract the tokens received from the order result
        our_tokens = float(result.get("size", 0) or result.get("tokens", 0) or 0)
        our_tx_hash = result.get("transaction_hash")

        # Step 5: Record the position so we can mirror the trader's future sell
        state.record_buy(
            condition_id=condition_id,
            outcome=outcome,
            slug=slug,
            title=title,
            trader_address=trader_address,
            trader_usdc_size=trader_usdc_spent,
            our_tokens=our_tokens,
            our_usdc_spent=size,
        )

        trade_log.log_buy_executed(
            trader_address=trader_address,
            slug=slug,
            condition_id=condition_id,
            outcome=outcome,
            title=title,
            trader_usdc_size=trader_usdc_spent,
            our_usdc_size=size,
            our_tokens=our_tokens,
            trader_portfolio_est=trader_portfolio,
            own_balance=own_balance,
            trade_pct=trade_pct,
            their_tx_hash=their_tx_hash,
            our_tx_hash=our_tx_hash,
        )

        logger.info("BUY order placed — tx: %s | tokens received: %.4f", our_tx_hash, our_tokens)
        return True

    except Exception as exc:
        err = str(exc)
        logger.error("BUY failed for '%s': %s", title, err)
        trade_log.log_failed("BUY_FAILED", trader_address, slug, condition_id, outcome, title, their_tx_hash, err)
        return False


def _execute_sell(trade: Dict) -> bool:
    """Mirror a SELL trade proportionally against our held position.

    Calculates the % of the tracked trader's position they sold,
    then sells the same % of our own token balance for that market.
    If we have no position on record, the sell is skipped and logged.

    Args:
        trade: Trade dict with side == "SELL".

    Returns:
        True if the sell was placed successfully, False otherwise.
    """
    trader_address = trade["trader_address"]
    condition_id = trade["condition_id"]
    outcome = trade["outcome"]
    slug = trade["slug"]
    title = trade.get("title", slug)
    trader_usdc_sold = float(trade["usdc_size"])
    their_tx_hash = trade.get("transaction_hash", "")

    # Look up our current position for this market outcome
    pos = state.get_position(condition_id, outcome)

    if not pos:
        # We don't hold this outcome — nothing to sell
        logger.info("SELL signal for '%s' → %s but we hold no position — skipping", title, outcome)
        return False

    our_tokens = pos["our_tokens"]
    trader_record = pos["traders"].get(trader_address)

    if trader_record and trader_record.get("usdc_size", 0) > 0:
        # Calculate sell % from how much of their original position they sold
        trader_original_usdc = trader_record["usdc_size"]
        sell_pct = min(trader_usdc_sold / trader_original_usdc, 1.0)
    else:
        # State was recovered from live Bullpen data — we don't have the original
        # buy size for this trader, so sell everything conservatively
        logger.warning(
            "No buy record for trader %s on '%s' (recovered state) — selling full position",
            trader_address, title,
        )
        sell_pct = 1.0

    tokens_to_sell = round(our_tokens * sell_pct, 6)

    if tokens_to_sell < 0.001:
        msg = f"Tokens to sell ({tokens_to_sell:.6f}) is below dust threshold"
        logger.info("%s — skipping SELL on '%s'", msg, title)
        trade_log.log_failed("SELL_SKIPPED", trader_address, slug, condition_id, outcome, title, their_tx_hash, msg)
        return False

    logger.info(
        "SELL '%s' → %s | trader sold %.2f%% → we sell %.2f%% = %.4f tokens",
        title, outcome, sell_pct * 100, sell_pct * 100, tokens_to_sell,
    )

    try:
        result = bullpen.place_sell(condition_id, outcome, tokens_to_sell)
        our_tx_hash = result.get("transaction_hash")

        # Extract USDC received from the sell result for realized PnL tracking
        usdc_received = float(result.get("usdc_size", 0) or result.get("cash", 0) or 0)

        # Update our position state to reflect the sold tokens
        state.update_after_sell(condition_id, outcome, tokens_to_sell)

        trade_log.log_sell_executed(
            trader_address=trader_address,
            slug=slug,
            condition_id=condition_id,
            outcome=outcome,
            title=title,
            sell_pct=sell_pct,
            tokens_sold=tokens_to_sell,
            usdc_received=usdc_received,
            their_tx_hash=their_tx_hash,
            our_tx_hash=our_tx_hash,
        )

        logger.info("SELL order placed — tx: %s | tokens sold: %.4f", our_tx_hash, tokens_to_sell)
        return True

    except Exception as exc:
        err = str(exc)
        logger.error("SELL failed for '%s': %s", title, err)
        trade_log.log_failed("SELL_FAILED", trader_address, slug, condition_id, outcome, title, their_tx_hash, err)
        return False
