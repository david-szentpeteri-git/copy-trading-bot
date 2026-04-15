"""Thin wrapper around the Bullpen CLI.

All subprocess calls to `bullpen` go through this module so the rest
of the codebase never has to deal with JSON parsing or subprocess errors
directly.

When dry run mode is active, place_buy() and place_sell() return a
simulated result using the live market price instead of executing real
orders. All other read-only calls (prices, positions, activity) always
hit the real API so PnL data stays realistic.
"""

import json
import subprocess
import sys
import uuid
from typing import Any, Dict, List, Optional

from config import config


def _run(args: List[str]) -> Any:
    """Execute a bullpen CLI command and return the parsed JSON output.

    On Windows, prefixes the command with `wsl` so the Linux bullpen
    binary inside WSL is invoked transparently.

    Args:
        args: CLI arguments to pass after `bullpen`, e.g.
              ["polymarket", "activity", "--address", "0x..."].

    Returns:
        Parsed JSON response (list or dict depending on the command).

    Raises:
        RuntimeError: If the CLI exits with a non-zero status code.
        json.JSONDecodeError: If the output is not valid JSON.
    """
    bullpen_cmd = [config.bullpen_bin] + args + ["--output", "json"]

    # On Windows the bullpen binary lives inside WSL — prefix with `wsl` to cross the boundary
    cmd = (["wsl"] + bullpen_cmd) if sys.platform == "win32" else bullpen_cmd

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"bullpen command failed: {' '.join(cmd)}\n"
            f"stderr: {result.stderr.strip()}"
        )

    return json.loads(result.stdout)


def get_recent_trades(address: str, since: Optional[str] = None, limit: int = 50) -> List[Dict]:
    """Fetch recent trades for a given Polymarket wallet address.

    Args:
        address: Polymarket proxy wallet address to query.
        since: ISO 8601 timestamp — only return trades after this time.
        limit: Maximum number of results to fetch.

    Returns:
        List of trade dicts, each containing at minimum:
        - transaction_hash (str)
        - timestamp (str, ISO 8601)
        - condition_id (str)
        - outcome_index (int)
        - side (str): "BUY" or "SELL"
        - usdc_size (float)
        - price (float)
        - title (str)
        - outcome (str)
    """
    args = [
        "polymarket", "activity",
        "--address", address,
        "--type", "trade",
        "--limit", str(limit),
    ]

    if since:
        args += ["--start", since]

    return _run(args)


def get_positions(address: str) -> List[Dict]:
    """Fetch all open positions for a wallet address.

    Used to estimate the trader's current portfolio value.

    Args:
        address: Polymarket proxy wallet address.

    Returns:
        List of position dicts with current value data.
    """
    return _run(["polymarket", "positions", "--address", address])


def get_own_balances() -> Dict:
    """Fetch the bot's own Polymarket USDC balance.

    Returns:
        Dict containing balance information including 'polymarket' USDC amount.
    """
    return _run(["portfolio", "balances"])


def get_price(condition_id: str, outcome: str) -> Optional[float]:
    """Fetch the current midpoint price for a market outcome.

    Used to calculate unrealized PnL on open positions.

    Args:
        condition_id: Polymarket market condition ID.
        outcome: Outcome label (e.g. "Yes", "Trail Blazers").

    Returns:
        Midpoint price as a float (0.0–1.0), or None if unavailable.
    """
    try:
        data = _run(["polymarket", "price", condition_id, outcome])
        # Bullpen returns a dict with 'mid', 'best_bid', 'best_ask', etc.
        return float(data.get("mid") or data.get("last") or 0)
    except Exception:
        return None


def get_own_positions() -> List[Dict]:
    """Fetch our own open Polymarket positions.

    Used to recover position state after a restart and for auto-redeem
    checks.

    Returns:
        List of position dicts. Each entry includes 'condition_id',
        'outcome', 'size' (token balance), and resolution status fields.
    """
    return _run(["polymarket", "positions"])


def place_buy(condition_id: str, outcome: str, amount_usdc: float) -> Dict:
    """Place a market buy order on Polymarket.

    In dry run mode, returns a simulated result using the live mid price
    to estimate tokens received — no real order is placed.

    Args:
        condition_id: The market's condition ID (hex string).
        outcome: The outcome label to buy (e.g. "Yes", "Trail Blazers").
        amount_usdc: Amount of USDC to spend on this trade.

    Returns:
        Dict with order confirmation details (real or simulated).

    Raises:
        RuntimeError: If the order fails to execute (live mode only).
    """
    import dry_run
    if dry_run.is_enabled():
        # Simulate the buy using the live price to estimate token quantity
        price = get_price(condition_id, outcome) or 0.5
        simulated_tokens = round(amount_usdc / price, 6) if price > 0 else 0
        return {
            "transaction_hash": f"DRY_RUN_{uuid.uuid4().hex[:16]}",
            "size": simulated_tokens,
            "usdc_size": amount_usdc,
            "price": price,
            "dry_run": True,
        }

    return _run([
        "polymarket", "buy",
        condition_id,
        outcome,
        str(amount_usdc),
    ])


def place_sell(condition_id: str, outcome: str, amount_tokens: float) -> Dict:
    """Place a market sell order on Polymarket.

    In dry run mode, returns a simulated result using the live mid price
    to estimate USDC received — no real order is placed.

    Args:
        condition_id: The market's condition ID (hex string).
        outcome: The outcome label to sell (e.g. "Yes", "Trail Blazers").
        amount_tokens: Number of outcome tokens to sell.

    Returns:
        Dict with order confirmation details (real or simulated).

    Raises:
        RuntimeError: If the order fails to execute (live mode only).
    """
    import dry_run
    if dry_run.is_enabled():
        # Simulate the sell using the live price to estimate USDC received
        price = get_price(condition_id, outcome) or 0.5
        simulated_usdc = round(amount_tokens * price, 6)
        return {
            "transaction_hash": f"DRY_RUN_{uuid.uuid4().hex[:16]}",
            "usdc_size": simulated_usdc,
            "size": amount_tokens,
            "price": price,
            "dry_run": True,
        }

    return _run([
        "polymarket", "sell",
        condition_id,
        outcome,
        str(amount_tokens),
    ])


def redeem_position(condition_id: str) -> Dict:
    """Redeem resolved winning tokens for USDC.

    Called automatically when the bot detects a market in our position
    state has resolved in our favour.

    Args:
        condition_id: Polymarket market condition ID of the resolved market.

    Returns:
        Dict with redemption confirmation details from the CLI.

    Raises:
        RuntimeError: If the redemption fails.
    """
    return _run(["polymarket", "redeem", condition_id])
