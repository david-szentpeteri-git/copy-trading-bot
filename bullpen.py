"""Thin wrapper around the Bullpen CLI.

All subprocess calls to `bullpen` go through this module so the rest
of the codebase never has to deal with JSON parsing or subprocess errors
directly.
"""

import json
import subprocess
from typing import Any, Dict, List, Optional

from config import config


def _run(args: List[str]) -> Any:
    """Execute a bullpen CLI command and return the parsed JSON output.

    Args:
        args: CLI arguments to pass after `bullpen`, e.g.
              ["polymarket", "activity", "--address", "0x..."].

    Returns:
        Parsed JSON response (list or dict depending on the command).

    Raises:
        RuntimeError: If the CLI exits with a non-zero status code.
        json.JSONDecodeError: If the output is not valid JSON.
    """
    cmd = [config.bullpen_bin] + args + ["--output", "json"]
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


def get_own_positions() -> List[Dict]:
    """Fetch our own open Polymarket positions.

    Used to recover position state after a restart when the local
    positions file is unavailable.

    Returns:
        List of position dicts. Each entry includes 'condition_id',
        'outcome', and 'size' (token balance).
    """
    return _run(["polymarket", "positions"])


def place_buy(condition_id: str, outcome: str, amount_usdc: float) -> Dict:
    """Place a market buy order on Polymarket.

    Args:
        condition_id: The market's condition ID (hex string).
        outcome: The outcome label to buy (e.g. "Yes", "Trail Blazers").
        amount_usdc: Amount of USDC to spend on this trade.

    Returns:
        Dict with order confirmation details from the CLI.

    Raises:
        RuntimeError: If the order fails to execute.
    """
    return _run([
        "polymarket", "buy",
        condition_id,
        outcome,
        str(amount_usdc),
    ])


def place_sell(condition_id: str, outcome: str, amount_tokens: float) -> Dict:
    """Place a market sell order on Polymarket.

    Args:
        condition_id: The market's condition ID (hex string).
        outcome: The outcome label to sell (e.g. "Yes", "Trail Blazers").
        amount_tokens: Number of outcome tokens to sell.

    Returns:
        Dict with order confirmation details from the CLI.

    Raises:
        RuntimeError: If the order fails to execute.
    """
    return _run([
        "polymarket", "sell",
        condition_id,
        outcome,
        str(amount_tokens),
    ])
