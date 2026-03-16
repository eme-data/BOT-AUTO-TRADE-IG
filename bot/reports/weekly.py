"""Weekly performance report generator.

Generates a formatted Telegram message summarizing the week's trading
performance. Scheduled to run every Sunday at 20:00 UTC.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import structlog
from sqlalchemy import select, func as sa_func

from bot.db.models import Trade
from bot.db.session import async_session_factory
from bot.notifications import send_message

logger = structlog.get_logger()


async def generate_weekly_report() -> None:
    """Build and send the weekly performance report via Telegram."""
    now = datetime.utcnow()
    week_start = now - timedelta(days=7)

    async with async_session_factory() as session:
        # All closed trades this week
        result = await session.execute(
            select(Trade)
            .where(Trade.closed_at >= week_start)
            .where(Trade.status.in_(["CLOSED", "SHADOW"]))
            .order_by(Trade.closed_at.desc())
        )
        trades = list(result.scalars().all())

        # Strategy-level aggregation
        strat_result = await session.execute(
            select(
                Trade.strategy_name,
                sa_func.count(Trade.id).label("cnt"),
                sa_func.sum(Trade.profit).label("pnl"),
                sa_func.count(Trade.id).filter(Trade.profit > 0).label("wins"),
            )
            .where(Trade.closed_at >= week_start)
            .where(Trade.status == "CLOSED")
            .group_by(Trade.strategy_name)
        )
        strategies = strat_result.all()

    if not trades:
        await send_message(
            "\U0001f4ca <b>Rapport Hebdo</b>\n"
            f"Semaine du {week_start.strftime('%d/%m')} au {now.strftime('%d/%m/%Y')}\n\n"
            "Aucun trade cette semaine."
        )
        return

    # Overall stats
    closed = [t for t in trades if t.status == "CLOSED"]
    shadow = [t for t in trades if t.status == "SHADOW"]
    total_pnl = sum(t.profit or 0 for t in closed)
    winners = [t for t in closed if (t.profit or 0) > 0]
    losers = [t for t in closed if (t.profit or 0) <= 0]
    win_rate = len(winners) / len(closed) * 100 if closed else 0
    best_trade = max(closed, key=lambda t: t.profit or 0) if closed else None
    worst_trade = min(closed, key=lambda t: t.profit or 0) if closed else None
    avg_pnl = total_pnl / len(closed) if closed else 0

    # Build message
    pnl_emoji = "\U0001f4c8" if total_pnl >= 0 else "\U0001f4c9"
    sign = "+" if total_pnl >= 0 else ""

    lines = [
        f"\U0001f4ca <b>Rapport Hebdo</b>",
        f"Semaine du {week_start.strftime('%d/%m')} au {now.strftime('%d/%m/%Y')}",
        "",
        f"{pnl_emoji} <b>P&L: {sign}{total_pnl:.2f} EUR</b>",
        f"\U0001f4b0 Trades: {len(closed)} ({len(winners)}W / {len(losers)}L)",
        f"\U0001f3af Win rate: {win_rate:.1f}%",
        f"\U0001f4ca P&L moyen: {avg_pnl:.2f} EUR",
    ]

    if best_trade:
        lines.append(f"\U0001f31f Meilleur: {best_trade.epic} +{best_trade.profit:.2f}")
    if worst_trade and (worst_trade.profit or 0) < 0:
        lines.append(f"\U0001f534 Pire: {worst_trade.epic} {worst_trade.profit:.2f}")

    if shadow:
        lines.append(f"\n\U0001f47b Shadow: {len(shadow)} trades paper")

    # Strategy breakdown
    if strategies:
        lines.append("\n<b>Par strategie:</b>")
        for s in strategies:
            s_pnl = float(s.pnl or 0)
            s_wr = s.wins / s.cnt * 100 if s.cnt else 0
            s_sign = "+" if s_pnl >= 0 else ""
            name = (s.strategy_name or "unknown").replace("ap_", "")
            lines.append(f"  {name}: {s.cnt} trades, {s_sign}{s_pnl:.2f} EUR ({s_wr:.0f}%W)")

    await send_message("\n".join(lines))
    logger.info("weekly_report_sent", trades=len(closed), pnl=total_pnl)
