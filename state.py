"""Active position state manager.

Persists a record of every market position the bot currently holds,
including the tokens received and the per-trader buy history needed
to calculate proportional sell sizes.

State is written to disk after every change so a restart doesn't lose
position data. On restart, if the file is missing, the bot recovers
live position data from the Bullpen CLI.
"""

import json
import logging
import os
from typing import Dict, Optional

import bullpen
from config import config

logger = logging.getLogger(__name__)

# In-memory state: keyed by "{condition_id}:{outcome}"
# Each value is a dict with our position details and per-trader buy records.
_positions: Dict[str, Dict] = {}


def _position_key(condition_id: str, outcome: str) -> str:
    """Build the dict key used to look up a position.

    Args:
        condition_id: Polymarket market condition ID.
        outcome: Outcome label (e.g. "Yes", "Trail Blazers").

    Returns:
        Composite string key.
    """
    return f"{condition_id}:{outcome}"


def load() -> None:
    """Load position state from disk into memory.

    If the file does not exist, attempts to recover state by querying
    our live Polymarket positions via Bullpen. Logs a warning if
    recovery also fails — the bot will operate without sell-side state
    until new BUY trades rebuild it.
    """
    global _positions

    if os.path.exists(config.positions_file):
        with open(config.positions_file, "r") as f:
            _positions = json.load(f)
        logger.info("Loaded %d active positions from %s", len(_positions), config.positions_file)
        return

    # File missing — try to recover from live Bullpen data
    logger.warning("Positions file not found at %s — attempting live recovery", config.positions_file)
    try:
        live = bullpen.get_own_positions()
        for pos in live:
            cid = pos.get("condition_id")
            outcome = pos.get("outcome")
            tokens = float(pos.get("size", 0))
            if cid and outcome and tokens > 0:
                key = _position_key(cid, outcome)
                # We don't know the per-trader history after recovery,
                # so store what we can and mark it as recovered
                _positions[key] = {
                    "condition_id": cid,
                    "outcome": outcome,
                    "slug": pos.get("slug", ""),
                    "title": pos.get("title", ""),
                    "our_tokens": tokens,
                    "our_usdc_spent": 0.0,  # unknown after recovery
                    "recovered": True,
                    "traders": {},  # per-trader buy records unavailable
                }
        logger.info("Recovered %d positions from live Bullpen data", len(_positions))
    except Exception as exc:
        logger.error("Live position recovery failed: %s — sell mirroring may be incomplete", exc)

    _save()


def _save() -> None:
    """Write the current in-memory state to disk.

    Creates the logs/ directory if it does not exist.
    """
    os.makedirs(os.path.dirname(config.positions_file), exist_ok=True)
    with open(config.positions_file, "w") as f:
        json.dump(_positions, f, indent=2)


def record_buy(
    condition_id: str,
    outcome: str,
    slug: str,
    title: str,
    trader_address: str,
    trader_usdc_size: float,
    our_tokens: float,
    our_usdc_spent: float,
) -> None:
    """Record a successful BUY in our position state.

    Creates a new position entry if this is the first time we're buying
    this outcome, or adds to an existing position if we already hold it
    (e.g. multiple tracked traders entered the same market).

    Args:
        condition_id: Polymarket market condition ID.
        outcome: Outcome label we bought.
        slug: Market URL slug (e.g. "nba-por-phx-2026-04-14").
        title: Human-readable market title.
        trader_address: Wallet address of the tracked trader we copied.
        trader_usdc_size: How much USDC the tracked trader spent (needed for sell % calc).
        our_tokens: Number of outcome tokens we received.
        our_usdc_spent: USDC we spent on this buy.
    """
    key = _position_key(condition_id, outcome)

    if key not in _positions:
        _positions[key] = {
            "condition_id": condition_id,
            "outcome": outcome,
            "slug": slug,
            "title": title,
            "our_tokens": 0.0,
            "our_usdc_spent": 0.0,
            "recovered": False,
            "traders": {},
        }

    pos = _positions[key]
    pos["our_tokens"] += our_tokens
    pos["our_usdc_spent"] += our_usdc_spent

    # Store per-trader buy record so we can calculate sell % later
    pos["traders"][trader_address] = {
        "usdc_size": trader_usdc_size,
        "sold": False,
    }

    _save()
    logger.debug("Recorded BUY: %s → %s (%.4f tokens)", title, outcome, our_tokens)


def get_position(condition_id: str, outcome: str) -> Optional[Dict]:
    """Look up our current position for a given market outcome.

    Args:
        condition_id: Polymarket market condition ID.
        outcome: Outcome label.

    Returns:
        Position dict if we hold this outcome, None otherwise.
    """
    return _positions.get(_position_key(condition_id, outcome))


def update_after_sell(condition_id: str, outcome: str, tokens_sold: float) -> None:
    """Reduce our token balance after a partial or full sell.

    Removes the position entirely if tokens drop to zero or below.

    Args:
        condition_id: Polymarket market condition ID.
        outcome: Outcome label we sold.
        tokens_sold: Number of tokens we sold.
    """
    key = _position_key(condition_id, outcome)
    if key not in _positions:
        return

    _positions[key]["our_tokens"] -= tokens_sold

    # Clean up fully closed positions
    if _positions[key]["our_tokens"] <= 0.001:
        del _positions[key]
        logger.debug("Position fully closed: %s", key)
    else:
        logger.debug(
            "Position partially closed: %s — %.4f tokens remaining",
            key, _positions[key]["our_tokens"],
        )

    _save()
