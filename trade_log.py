"""Append-only JSON trade log for performance tracking and dashboard use.

Every trade event (executed, failed, or skipped) is appended as a
single JSON object on its own line (newline-delimited JSON / NDJSON).
This format is easy to stream, parse incrementally, and query later.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from config import config

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _append(entry: Dict[str, Any]) -> None:
    """Append a single log entry to the NDJSON trade log file.

    Creates the logs/ directory if it does not exist.

    Args:
        entry: Dict to serialise and append as one JSON line.
    """
    os.makedirs(os.path.dirname(config.trade_log_file), exist_ok=True)
    with open(config.trade_log_file, "a") as f:
        f.write(json.dumps(entry) + "\n")


def log_redeemed(
    condition_id: str,
    outcome: str,
    title: str,
    slug: str,
    usdc_redeemed: float,
) -> None:
    """Log a successful automatic redemption of resolved winning tokens.

    Args:
        condition_id: Polymarket condition ID of the resolved market.
        outcome: The winning outcome we held.
        title: Human-readable market title.
        slug: Market URL slug.
        usdc_redeemed: USDC received from the redemption.
    """
    _append({
        "event": "REDEEMED",
        "timestamp": _now_iso(),
        "condition_id": condition_id,
        "outcome": outcome,
        "title": title,
        "slug": slug,
        "usdc_redeemed": usdc_redeemed,
        "dry_run": False,
        "error": None,
    })


def log_buy_executed(
    trader_address: str,
    slug: str,
    condition_id: str,
    outcome: str,
    title: str,
    trader_usdc_size: float,
    our_usdc_size: float,
    our_tokens: float,
    trader_portfolio_est: float,
    own_balance: float,
    trade_pct: float,
    their_tx_hash: str,
    our_tx_hash: Optional[str] = None,
    is_dry_run: bool = False,
) -> None:
    """Log a successfully executed BUY copy trade.

    Args:
        trader_address: Tracked wallet we copied.
        slug: Market URL slug.
        condition_id: Polymarket condition ID.
        outcome: Outcome label purchased.
        title: Human-readable market title.
        trader_usdc_size: USDC the tracked trader spent.
        our_usdc_size: USDC we spent.
        our_tokens: Number of outcome tokens we received.
        trader_portfolio_est: Estimated portfolio value of the tracked trader.
        own_balance: Our USDC balance at time of trade.
        trade_pct: Portfolio fraction used (0.0–1.0).
        their_tx_hash: Transaction hash of the copied trade.
        our_tx_hash: Transaction hash of our executed order, if available.
        is_dry_run: True if this was a simulated trade, False for real.
    """
    _append({
        "event": "BUY_EXECUTED",
        "timestamp": _now_iso(),
        "copied_from": trader_address,
        "slug": slug,
        "condition_id": condition_id,
        "outcome": outcome,
        "title": title,
        "trader_usdc_size": trader_usdc_size,
        "our_usdc_size": our_usdc_size,
        "our_tokens": our_tokens,
        "trader_portfolio_est": trader_portfolio_est,
        "own_balance": own_balance,
        "trade_pct": round(trade_pct, 6),
        "their_tx_hash": their_tx_hash,
        "our_tx_hash": our_tx_hash,
        "dry_run": is_dry_run,
        "error": None,
    })


def log_sell_executed(
    trader_address: str,
    slug: str,
    condition_id: str,
    outcome: str,
    title: str,
    sell_pct: float,
    tokens_sold: float,
    usdc_received: float,
    their_tx_hash: str,
    our_tx_hash: Optional[str] = None,
    is_dry_run: bool = False,
) -> None:
    """Log a successfully executed SELL copy trade.

    Args:
        trader_address: Tracked wallet whose sell we mirrored.
        slug: Market URL slug.
        condition_id: Polymarket condition ID.
        outcome: Outcome label sold.
        title: Human-readable market title.
        sell_pct: Fraction of the trader's position they sold (0.0–1.0).
        tokens_sold: Number of tokens we sold.
        usdc_received: USDC received from the sell — used for realized PnL.
        their_tx_hash: Transaction hash of the tracked sell.
        our_tx_hash: Transaction hash of our sell order, if available.
        is_dry_run: True if this was a simulated trade, False for real.
    """
    _append({
        "event": "SELL_EXECUTED",
        "timestamp": _now_iso(),
        "copied_from": trader_address,
        "slug": slug,
        "condition_id": condition_id,
        "outcome": outcome,
        "title": title,
        "sell_pct": round(sell_pct, 6),
        "tokens_sold": tokens_sold,
        "usdc_received": usdc_received,
        "their_tx_hash": their_tx_hash,
        "our_tx_hash": our_tx_hash,
        "dry_run": is_dry_run,
        "error": None,
    })


def log_failed(
    event_type: str,
    trader_address: str,
    slug: str,
    condition_id: str,
    outcome: str,
    title: str,
    their_tx_hash: str,
    error: str,
) -> None:
    """Log a trade that failed to execute or was skipped with a reason.

    Args:
        event_type: One of "BUY_FAILED", "SELL_FAILED", "BUY_SKIPPED", "SELL_SKIPPED".
        trader_address: Tracked wallet address.
        slug: Market URL slug.
        condition_id: Polymarket condition ID.
        outcome: Outcome label.
        title: Human-readable market title.
        their_tx_hash: Transaction hash of the original trade.
        error: Human-readable reason for the failure or skip.
    """
    import dry_run as _dry_run
    _append({
        "event": event_type,
        "timestamp": _now_iso(),
        "copied_from": trader_address,
        "slug": slug,
        "condition_id": condition_id,
        "outcome": outcome,
        "title": title,
        "their_tx_hash": their_tx_hash,
        "dry_run": _dry_run.is_enabled(),
        "error": error,
    })
