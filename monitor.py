"""Trade monitor for tracked Polymarket wallets.

Polls each tracked trader's activity on a regular interval and yields
any new trades that have not been seen before.
"""

import json
import logging
import os
from datetime import datetime, timezone
from typing import Dict, Generator, List, Set

import bullpen
from config import config

logger = logging.getLogger(__name__)


def load_seen_trades() -> Set[str]:
    """Load the set of already-processed transaction hashes from disk.

    Returns:
        Set of transaction hash strings that have already been copied.
    """
    if not os.path.exists(config.seen_trades_file):
        return set()

    with open(config.seen_trades_file, "r") as f:
        return set(json.load(f))


def save_seen_trades(seen: Set[str]) -> None:
    """Persist the set of processed transaction hashes to disk.

    Args:
        seen: Set of transaction hash strings to persist.
    """
    # Ensure the directory exists before writing
    os.makedirs(os.path.dirname(config.seen_trades_file), exist_ok=True)

    with open(config.seen_trades_file, "w") as f:
        json.dump(list(seen), f)


def poll_new_trades(
    since_iso: str,
    seen_hashes: Set[str],
) -> Generator[Dict, None, None]:
    """Poll all tracked traders and yield trades not yet processed.

    For each configured trader address, fetches recent trades since
    `since_iso` and yields any whose transaction hash is not in
    `seen_hashes`.

    Args:
        since_iso: ISO 8601 timestamp — only consider trades after this.
        seen_hashes: Set of already-processed transaction hashes.

    Yields:
        Trade dicts enriched with a 'trader_address' field identifying
        which tracked wallet made the trade.
    """
    for address in config.traders:
        try:
            trades = bullpen.get_recent_trades(address, since=since_iso)
        except Exception as exc:
            logger.error("Failed to fetch trades for %s: %s", address, exc)
            continue

        for trade in trades:
            tx_hash = trade.get("transaction_hash")

            # Skip if we've already processed this transaction
            if tx_hash in seen_hashes:
                continue

            # Only copy BUY trades — selling is position management by the trader
            if trade.get("side", "").upper() != "BUY":
                seen_hashes.add(tx_hash)
                continue

            # Attach the source trader address for downstream sizing logic
            trade["trader_address"] = address

            yield trade


def get_since_timestamp() -> str:
    """Return an ISO 8601 timestamp for one hour ago in UTC.

    Used as the initial lookback window on bot startup to avoid
    copying very stale trades from before the bot was launched.

    Returns:
        ISO 8601 formatted UTC timestamp string.
    """
    # On first run, look back 1 hour to catch any very recent trades
    # but avoid replaying the entire trade history
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    lookback = now - timedelta(hours=1)
    return lookback.strftime("%Y-%m-%dT%H:%M:%SZ")
