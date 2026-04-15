"""Streamlit dashboard for the Polymarket copy trading bot.

Displays at-a-glance stats (PnL, win rate, trade count), open positions
with live unrealized PnL, and a full trade history table. Includes a
button to start or stop the bot daemon. Auto-refreshes every 30 seconds.

Run with:
    streamlit run dashboard.py
"""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

import streamlit as st

import bot_control
import bullpen
from config import config

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Copy Bot Dashboard",
    page_icon="📈",
    layout="wide",
)

# Auto-refresh every 30 seconds using Streamlit's built-in rerun mechanism
st_autorefresh = st.empty()  # placeholder — actual refresh wired at the bottom


# ── Data loading ───────────────────────────────────────────────────────────────

def load_trade_log() -> List[Dict[str, Any]]:
    """Read all entries from the NDJSON trade log file.

    Returns:
        List of trade event dicts, newest-first. Returns empty list if
        the log file does not exist yet.
    """
    log_path = Path(config.trade_log_file)
    if not log_path.exists():
        return []

    entries = []
    with open(log_path, "r") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Newest first so the table shows recent activity at the top
    return list(reversed(entries))


def load_positions() -> Dict[str, Any]:
    """Read our current active positions from the positions state file.

    Returns:
        Dict keyed by "condition_id:outcome", or empty dict if no file.
    """
    pos_path = Path(config.positions_file)
    if not pos_path.exists():
        return {}

    with open(pos_path, "r") as f:
        return json.load(f)


def fetch_live_prices(positions: Dict[str, Any]) -> Dict[str, float]:
    """Fetch current mid prices for all open positions from Bullpen.

    Args:
        positions: Position state dict from load_positions().

    Returns:
        Dict mapping "condition_id:outcome" to current price (0.0–1.0).
        Missing entries mean the price fetch failed.
    """
    prices = {}
    for key, pos in positions.items():
        price = bullpen.get_price(pos["condition_id"], pos["outcome"])
        if price is not None:
            prices[key] = price
    return prices


# ── PnL calculation ────────────────────────────────────────────────────────────

def compute_stats(
    trades: List[Dict],
    positions: Dict[str, Any],
    prices: Dict[str, float],
) -> Dict[str, Any]:
    """Compute all KPI stats from trade log + live position data.

    Win/loss rules:
    - SELL_EXECUTED: win if usdc_received > proportional cost basis, else loss
    - Open positions: PENDING (not counted in win rate)

    Args:
        trades: All entries from the trade log.
        positions: Active positions dict.
        prices: Live prices keyed by "condition_id:outcome".

    Returns:
        Dict with keys: total_executed, wins, losses, pending,
        win_rate, realized_pnl, unrealized_pnl.
    """
    # Build a cost-basis map: condition_id:outcome → usdc_spent
    # Used to calculate realized PnL on sells
    cost_basis: Dict[str, float] = {}
    for t in reversed(trades):  # process chronologically
        if t["event"] == "BUY_EXECUTED":
            key = f"{t['condition_id']}:{t['outcome']}"
            cost_basis[key] = cost_basis.get(key, 0) + t.get("our_usdc_size", 0)

    wins = 0
    losses = 0
    realized_pnl = 0.0
    executed_count = 0

    for t in trades:
        if t["event"] == "BUY_EXECUTED":
            executed_count += 1

        elif t["event"] == "SELL_EXECUTED":
            usdc_received = t.get("usdc_received", 0)
            sell_pct = t.get("sell_pct", 1.0)
            key = f"{t['condition_id']}:{t['outcome']}"
            total_cost = cost_basis.get(key, 0)

            # Proportional cost for the portion we sold
            cost_for_this_sell = total_cost * sell_pct
            pnl = usdc_received - cost_for_this_sell
            realized_pnl += pnl

            if pnl >= 0:
                wins += 1
            else:
                losses += 1

    # Pending = open positions we've bought but not sold yet
    pending = len(positions)

    # Win rate excludes pending trades
    closed = wins + losses
    win_rate = (wins / closed * 100) if closed > 0 else 0.0

    # Unrealized PnL: current market value minus what we paid
    unrealized_pnl = 0.0
    for key, pos in positions.items():
        price = prices.get(key)
        if price is not None:
            current_value = price * pos["our_tokens"]
            unrealized_pnl += current_value - pos["our_usdc_spent"]

    return {
        "total_executed": executed_count,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "win_rate": win_rate,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
    }


# ── Rendering helpers ──────────────────────────────────────────────────────────

def _pnl_str(value: float) -> str:
    """Format a PnL value with a +/- prefix and $ sign.

    Args:
        value: Dollar amount, positive or negative.

    Returns:
        Formatted string like "+$4.20" or "-$1.50".
    """
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:.2f}"


def _colour(value: float) -> str:
    """Return a green or red hex colour based on whether value is positive.

    Args:
        value: Numeric value to evaluate.

    Returns:
        CSS hex colour string.
    """
    return "#00c853" if value >= 0 else "#d50000"


# ── Main dashboard ─────────────────────────────────────────────────────────────

def render() -> None:
    """Render the full dashboard UI."""

    # ── Header ────────────────────────────────────────────────────────────────
    col_title, col_bot = st.columns([3, 1])

    with col_title:
        st.title("📈 Polymarket Copy Bot")

    with col_bot:
        st.markdown("### Bot Control")
        running = bot_control.is_running()

        if running:
            st.success("● BOT RUNNING")
            if st.button("🔴 Stop Bot", use_container_width=True):
                bot_control.stop()
                st.rerun()
        else:
            st.error("○ BOT STOPPED")
            if st.button("🟢 Start Bot", use_container_width=True):
                bot_control.start()
                st.rerun()

    st.divider()

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading trade data..."):
        trades = load_trade_log()
        positions = load_positions()
        prices = fetch_live_prices(positions)
        stats = compute_stats(trades, positions, prices)

    # ── KPI row ───────────────────────────────────────────────────────────────
    st.subheader("Overview")
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)

    k1.metric("Trades Executed", stats["total_executed"])
    k2.metric("Win Rate", f"{stats['win_rate']:.1f}%")
    k3.metric("Winners ✅", stats["wins"])
    k4.metric("Losers ❌", stats["losses"])
    k5.metric("Pending ⏳", stats["pending"])
    k6.metric(
        "Realized PnL",
        _pnl_str(stats["realized_pnl"]),
        delta=None,
    )
    k7.metric(
        "Unrealized PnL",
        _pnl_str(stats["unrealized_pnl"]),
        delta=None,
    )

    st.divider()

    # ── Open positions ────────────────────────────────────────────────────────
    st.subheader(f"⏳ Open Positions ({len(positions)})")

    if positions:
        rows = []
        for key, pos in positions.items():
            price = prices.get(key)
            current_value = (price * pos["our_tokens"]) if price is not None else None
            unrealized = (current_value - pos["our_usdc_spent"]) if current_value is not None else None

            rows.append({
                "Market": pos.get("title", pos.get("slug", key)),
                "Outcome": pos["outcome"],
                "Tokens": f"{pos['our_tokens']:.4f}",
                "Paid (USDC)": f"${pos['our_usdc_spent']:.2f}",
                "Current Price": f"{price:.3f}" if price is not None else "—",
                "Current Value": f"${current_value:.2f}" if current_value is not None else "—",
                "Unrealized PnL": _pnl_str(unrealized) if unrealized is not None else "—",
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No open positions.")

    st.divider()

    # ── Trade history ─────────────────────────────────────────────────────────
    st.subheader("📋 Trade History")

    executed_trades = [
        t for t in trades
        if t["event"] in ("BUY_EXECUTED", "SELL_EXECUTED", "BUY_FAILED", "SELL_FAILED")
    ]

    if executed_trades:
        rows = []
        for t in executed_trades:
            event = t["event"]

            if event == "BUY_EXECUTED":
                action = "BUY"
                amount = f"${t.get('our_usdc_size', 0):.2f}"
                result = "OPEN"
                pnl = "—"
            elif event == "SELL_EXECUTED":
                action = "SELL"
                received = t.get("usdc_received", 0)
                amount = f"${t.get('tokens_sold', 0):.4f} tokens"
                result_val = received
                pnl = _pnl_str(result_val) if result_val else "—"
                result = "WIN ✅" if received > 0 else "LOSS ❌"
            else:
                action = event.replace("_", " ")
                amount = "—"
                result = "FAILED ❌"
                pnl = "—"

            rows.append({
                "Time (UTC)": t["timestamp"][:16].replace("T", " "),
                "Market": t.get("title", t.get("slug", ""))[:45],
                "Outcome": t.get("outcome", ""),
                "Action": action,
                "Amount": amount,
                "PnL": pnl,
                "Result": result,
                "Copied From": t.get("copied_from", "")[:10] + "...",
            })

        st.dataframe(rows, use_container_width=True, hide_index=True)
    else:
        st.info("No trades executed yet. Start the bot to begin copy trading.")

    # ── Footer ────────────────────────────────────────────────────────────────
    st.caption(f"Auto-refreshes every {config.poll_interval_seconds}s · Tracking {len(config.traders)} traders")


# ── Entry point ────────────────────────────────────────────────────────────────
render()

# Wire up the 30-second auto-refresh after the page has rendered
# st_autorefresh from streamlit-autorefresh package handles this cleanly
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30_000, key="dashboard_refresh")
except ImportError:
    # Graceful fallback: show a manual refresh button if the package isn't installed
    if st.button("🔄 Refresh"):
        st.rerun()
