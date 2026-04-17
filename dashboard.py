"""Streamlit dashboard for the Polymarket copy trading bot.

Shows at-a-glance KPIs (PnL, win rate, trade count), open positions with
live unrealized PnL, and two trade history tables (real vs dry run) in the
same tab. Includes bot on/off and dry run toggle buttons.

Auto-refreshes every 30 seconds.

Run with:
    streamlit run dashboard.py
"""

import json
from pathlib import Path
from typing import Any, Dict, List

import streamlit as st

import bot_control
import bullpen
import dry_run
import no_duplicates
from config import config

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Copy Bot Dashboard",
    page_icon="📈",
    layout="wide",
)


# ── Data loading ───────────────────────────────────────────────────────────────

def load_trade_log() -> List[Dict[str, Any]]:
    """Read all entries from the NDJSON trade log file.

    Returns:
        List of trade event dicts, newest-first. Empty list if file
        does not exist yet.
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

    # Newest first so tables show recent activity at the top
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
    """
    prices = {}
    for key, pos in positions.items():
        price = bullpen.get_price(pos["slug"], pos["outcome"])
        if price is not None:
            prices[key] = price
    return prices


# ── PnL / stats calculation ────────────────────────────────────────────────────

def compute_stats(
    trades: List[Dict],
    positions: Dict[str, Any],
    prices: Dict[str, float],
    real_only: bool,
) -> Dict[str, Any]:
    """Compute KPI stats for either real trades or dry run trades.

    Args:
        trades: All entries from the trade log.
        positions: Active positions dict.
        prices: Live prices keyed by "condition_id:outcome".
        real_only: If True, compute stats for real trades only.
                   If False, compute for dry run trades only.

    Returns:
        Dict with keys: total_executed, wins, losses, pending,
        win_rate, realized_pnl, unrealized_pnl.
    """
    # Filter log to the requested trade type
    relevant = [t for t in trades if bool(t.get("dry_run")) != real_only]

    # Build cost basis map for sell PnL calculation
    cost_basis: Dict[str, float] = {}
    for t in reversed(relevant):
        if t["event"] == "BUY_EXECUTED":
            key = f"{t['condition_id']}:{t['outcome']}"
            cost_basis[key] = cost_basis.get(key, 0) + t.get("our_usdc_size", 0)

    wins = losses = executed_count = 0
    realized_pnl = 0.0

    for t in relevant:
        if t["event"] == "BUY_EXECUTED":
            executed_count += 1
        elif t["event"] == "SELL_EXECUTED":
            usdc_received = t.get("usdc_received", 0)
            sell_pct = t.get("sell_pct", 1.0)
            key = f"{t['condition_id']}:{t['outcome']}"
            cost_for_this_sell = cost_basis.get(key, 0) * sell_pct
            pnl = usdc_received - cost_for_this_sell
            realized_pnl += pnl
            if pnl >= 0:
                wins += 1
            else:
                losses += 1

    pending = len(positions)
    closed = wins + losses
    win_rate = (wins / closed * 100) if closed > 0 else 0.0

    # Unrealized PnL from open positions using live prices
    unrealized_pnl = 0.0
    for key, pos in positions.items():
        # Only count positions that match the current mode (real vs dry run)
        if bool(pos.get("dry_run")) == real_only:
            continue
        price = prices.get(key)
        if price is not None:
            unrealized_pnl += (price * pos["our_tokens"]) - pos["our_usdc_spent"]

    return {
        "total_executed": executed_count,
        "wins": wins,
        "losses": losses,
        "pending": pending,
        "win_rate": win_rate,
        "realized_pnl": realized_pnl,
        "unrealized_pnl": unrealized_pnl,
    }


# ── Formatting helpers ─────────────────────────────────────────────────────────

def _pnl_str(value: float) -> str:
    """Format a PnL value with sign and dollar symbol."""
    sign = "+" if value >= 0 else ""
    return f"{sign}${value:.2f}"


def _render_kpis(stats: Dict[str, Any]) -> None:
    """Render the 7-column KPI row.

    Args:
        stats: Output of compute_stats().
    """
    k1, k2, k3, k4, k5, k6, k7 = st.columns(7)
    k1.metric("Trades Executed", stats["total_executed"])
    k2.metric("Win Rate", f"{stats['win_rate']:.1f}%")
    k3.metric("Winners ✅", stats["wins"])
    k4.metric("Losers ❌", stats["losses"])
    k5.metric("Pending ⏳", stats["pending"])
    k6.metric("Realized PnL", _pnl_str(stats["realized_pnl"]))
    k7.metric("Unrealized PnL", _pnl_str(stats["unrealized_pnl"]))


def _render_positions(positions: Dict, prices: Dict) -> None:
    """Render the open positions table.

    Args:
        positions: Active positions dict.
        prices: Live prices dict.
    """
    if not positions:
        st.info("No open positions.")
        return

    rows = []
    for key, pos in positions.items():
        price = prices.get(key)
        current_value = (price * pos["our_tokens"]) if price is not None else None
        unrealized = (current_value - pos["our_usdc_spent"]) if current_value is not None else None
        rows.append({
            "Market": pos.get("title", pos.get("slug", key))[:50],
            "Outcome": pos["outcome"],
            "Tokens": f"{pos['our_tokens']:.4f}",
            "Paid (USDC)": f"${pos['our_usdc_spent']:.2f}",
            "Current Price": f"{price:.3f}" if price is not None else "—",
            "Current Value": f"${current_value:.2f}" if current_value is not None else "—",
            "Unrealized PnL": _pnl_str(unrealized) if unrealized is not None else "—",
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_trade_table(trades: List[Dict], is_dry: bool) -> None:
    """Render a trade history table filtered to real or dry run trades.

    Args:
        trades: All trade log entries (newest-first).
        is_dry: True to show dry run trades, False for real trades.
    """
    filtered = [
        t for t in trades
        if t["event"] in ("BUY_EXECUTED", "SELL_EXECUTED", "BUY_FAILED", "SELL_FAILED")
        and bool(t.get("dry_run")) == is_dry
    ]

    if not filtered:
        label = "dry run" if is_dry else "real"
        st.info(f"No {label} trades yet.")
        return

    rows = []
    for t in filtered:
        event = t["event"]
        if event == "BUY_EXECUTED":
            action, amount = "BUY", f"${t.get('our_usdc_size', 0):.2f}"
            result, pnl = "OPEN ⏳", "—"
        elif event == "SELL_EXECUTED":
            action = "SELL"
            amount = f"{t.get('tokens_sold', 0):.4f} tokens"
            received = t.get("usdc_received", 0)
            pnl = _pnl_str(received) if received else "—"
            result = "WIN ✅" if received > 0 else "LOSS ❌"
        else:
            action = event.replace("_", " ")
            amount, result, pnl = "—", "FAILED ❌", "—"

        rows.append({
            "Time (UTC)": t["timestamp"][:16].replace("T", " "),
            "Market": t.get("title", t.get("slug", ""))[:45],
            "Outcome": t.get("outcome", ""),
            "Action": action,
            "Amount": amount,
            "PnL": pnl,
            "Result": result,
            "Copied From": (t.get("copied_from", "") or "")[:10] + "...",
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)


def _render_trader_stats(trades: List[Dict]) -> None:
    """Render a per-trader breakdown of trade count, win rate, and PnL.

    Args:
        trades: All trade log entries (newest-first).
    """
    # Aggregate stats keyed by trader address
    stats: Dict[str, Dict] = {}

    # First pass: build cost basis per trader per market
    cost_basis: Dict[str, Dict[str, float]] = {}
    for t in reversed(trades):
        addr = t.get("copied_from") or t.get("trader_address", "unknown")
        if t["event"] == "BUY_EXECUTED":
            key = f"{t['condition_id']}:{t['outcome']}"
            cost_basis.setdefault(addr, {})
            cost_basis[addr][key] = cost_basis[addr].get(key, 0) + t.get("our_usdc_size", 0)

    for t in trades:
        addr = t.get("copied_from") or t.get("trader_address", "unknown")
        if addr not in stats:
            stats[addr] = {"trades": 0, "wins": 0, "losses": 0, "realized_pnl": 0.0}

        if t["event"] == "BUY_EXECUTED":
            stats[addr]["trades"] += 1
        elif t["event"] == "SELL_EXECUTED":
            usdc_received = t.get("usdc_received", 0)
            sell_pct = t.get("sell_pct", 1.0)
            key = f"{t['condition_id']}:{t['outcome']}"
            cost = cost_basis.get(addr, {}).get(key, 0) * sell_pct
            pnl = usdc_received - cost
            stats[addr]["realized_pnl"] += pnl
            if pnl >= 0:
                stats[addr]["wins"] += 1
            else:
                stats[addr]["losses"] += 1

    if not stats:
        st.info("No trader data yet.")
        return

    rows = []
    for addr, s in stats.items():
        closed = s["wins"] + s["losses"]
        win_rate = (s["wins"] / closed * 100) if closed > 0 else 0.0
        rows.append({
            "Trader": addr[:10] + "..." + addr[-6:],
            "Trades Copied": s["trades"],
            "Wins": s["wins"],
            "Losses": s["losses"],
            "Win Rate": f"{win_rate:.1f}%",
            "Realized PnL": _pnl_str(s["realized_pnl"]),
        })

    st.dataframe(rows, use_container_width=True, hide_index=True)


# ── Main dashboard ─────────────────────────────────────────────────────────────

def render() -> None:
    """Render the full dashboard UI."""

    # ── Dry run banner ────────────────────────────────────────────────────────
    if dry_run.is_enabled():
        st.warning("🧪 **DRY RUN MODE ACTIVE** — No real orders are being placed. All PnL is simulated using live market prices.")

    # ── Header row ────────────────────────────────────────────────────────────
    col_title, col_controls = st.columns([3, 2])

    with col_title:
        st.title("📈 Polymarket Copy Bot")

    with col_controls:
        st.markdown("### Controls")
        c1, c2 = st.columns(2)

        # Bot on/off button
        with c1:
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

        # Dry run toggle
        with c2:
            if dry_run.is_enabled():
                st.info("🧪 DRY RUN ON")
                if st.button("Switch to Live", use_container_width=True):
                    dry_run.disable()
                    st.rerun()
            else:
                st.success("💰 LIVE MODE")
                if st.button("Enable Dry Run", use_container_width=True):
                    dry_run.enable()
                    st.rerun()

    # ── Secondary controls row ────────────────────────────────────────────────
    c3, c4 = st.columns([1, 3])
    with c3:
        if no_duplicates.is_enabled():
            st.info("🚫 Skip Duplicates: ON")
            if st.button("Allow duplicate buys", use_container_width=True):
                no_duplicates.disable()
                st.rerun()
        else:
            st.warning("♻️ Skip Duplicates: OFF")
            if st.button("Skip duplicate positions", use_container_width=True):
                no_duplicates.enable()
                st.rerun()

    with c4:
        st.markdown("&nbsp;", unsafe_allow_html=True)
        if st.button("🗑️ Clear Dry Run History", use_container_width=False):
            result = dry_run.reset_dry_run_data()
            st.success(
                f"Cleared {result['removed_trades']} dry run trades, "
                f"{result['removed_positions']} positions. "
                "Bot will replay recent trades on next poll."
            )
            st.rerun()

    st.divider()

    # ── Load data ─────────────────────────────────────────────────────────────
    with st.spinner("Loading data..."):
        trades = load_trade_log()
        positions = load_positions()
        prices = fetch_live_prices(positions)
        real_stats = compute_stats(trades, positions, prices, real_only=True)
        dry_stats = compute_stats(trades, positions, prices, real_only=False)

    # ── Real trade stats ──────────────────────────────────────────────────────
    st.subheader("💰 Live Trading Performance")
    _render_kpis(real_stats)

    # ── Dry run stats ─────────────────────────────────────────────────────────
    st.subheader("🧪 Dry Run Performance")
    _render_kpis(dry_stats)

    st.divider()

    # ── Open positions ────────────────────────────────────────────────────────
    st.subheader(f"⏳ Open Positions ({len(positions)})")
    _render_positions(positions, prices)

    st.divider()

    # ── Trade history: two tables, same tab ───────────────────────────────────
    st.subheader("📋 Trade History")

    st.markdown("#### 💰 Real Trades")
    _render_trade_table(trades, is_dry=False)

    st.markdown("#### 🧪 Dry Run Trades")
    _render_trade_table(trades, is_dry=True)

    st.divider()

    # ── Per-trader stats ──────────────────────────────────────────────────────
    st.subheader("👤 Per-Trader Stats")
    _render_trader_stats(trades)

    # ── Footer ────────────────────────────────────────────────────────────────
    st.caption(
        f"Auto-refreshes every 30s · "
        f"Tracking {len(config.traders)} traders · "
        f"Mode: {'DRY RUN 🧪' if dry_run.is_enabled() else 'LIVE 💰'}"
    )


# ── Entry point ────────────────────────────────────────────────────────────────
render()

# Wire up 30-second auto-refresh
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30_000, key="dashboard_refresh")
except ImportError:
    if st.button("🔄 Refresh"):
        st.rerun()
