"""Auto-redeem module for resolved Polymarket positions.

Every poll cycle, check our own Polymarket positions for any markets
that have resolved in our favour. When winning tokens are found, redeem
them for USDC automatically and log the event.

Losing tokens (resolved against us) are ignored — they are worthless
and cannot be redeemed.
"""

import logging
from typing import List, Dict

import bullpen
import state
import trade_log

logger = logging.getLogger(__name__)

# A position is considered a winner if its resolved price is at or above this threshold.
# Winning tokens on Polymarket resolve to $1.00 each.
_WIN_PRICE_THRESHOLD = 0.99


def check_and_redeem() -> int:
    """Check for resolved winning positions and redeem them for USDC.

    Fetches our live Polymarket positions, identifies any that have
    resolved in our favour (price ≈ 1.0), and calls bullpen redeem
    for each. The position is removed from local state after redemption.

    Returns:
        Number of positions successfully redeemed this cycle.
    """
    try:
        positions = bullpen.get_own_positions()
    except Exception as exc:
        logger.warning("Could not fetch own positions for redeem check: %s", exc)
        return 0

    redeemed_count = 0

    for pos in positions:
        condition_id = pos.get("condition_id")
        outcome = pos.get("outcome", "")
        title = pos.get("title", condition_id)
        slug = pos.get("slug", "")

        if not condition_id:
            continue

        # Check if the market has resolved — Bullpen may expose this via
        # 'resolved', 'is_resolved', or a price of exactly 1.0 or 0.0
        is_resolved = _is_resolved_winner(pos)

        if not is_resolved:
            continue

        token_balance = float(pos.get("size", 0) or 0)
        if token_balance <= 0:
            continue

        logger.info(
            "Resolved winning position detected: '%s' → %s (%.4f tokens) — redeeming",
            title, outcome, token_balance,
        )

        try:
            result = bullpen.redeem_position(condition_id)

            # Each winning token redeems for $1.00 USDC
            usdc_redeemed = float(result.get("usdc_size", 0) or token_balance)

            # Remove this position from our local state since it's now closed
            state.update_after_sell(condition_id, outcome, token_balance)

            trade_log.log_redeemed(
                condition_id=condition_id,
                outcome=outcome,
                title=title,
                slug=slug,
                usdc_redeemed=usdc_redeemed,
            )

            logger.info(
                "Redeemed '%s' → %s for $%.2f USDC",
                title, outcome, usdc_redeemed,
            )
            redeemed_count += 1

        except Exception as exc:
            logger.error("Failed to redeem '%s': %s", title, exc)

    return redeemed_count


def _is_resolved_winner(pos: Dict) -> bool:
    """Determine whether a position represents a resolved winning outcome.

    Checks several fields that Bullpen may populate for resolved markets:
    - Explicit 'resolved' boolean
    - Current price at or above the win threshold (≈ 1.0)
    - 'redeemable' flag

    Args:
        pos: Position dict from bullpen.get_own_positions().

    Returns:
        True if the position appears to be a resolved winner.
    """
    # Explicit resolved flag from the API
    if pos.get("resolved") is True or pos.get("is_resolved") is True:
        price = float(pos.get("current_price", pos.get("price", 0)) or 0)
        return price >= _WIN_PRICE_THRESHOLD

    # Some Bullpen versions use a 'redeemable' field directly
    if pos.get("redeemable") is True:
        return True

    # Fall back to price signal: winning tokens trade at ~$1.00
    price = float(pos.get("current_price", pos.get("price", 0)) or 0)
    if price >= _WIN_PRICE_THRESHOLD:
        return True

    return False
