"""PDF report generation endpoint."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func as sa_func, select, cast, Date
from sqlalchemy.ext.asyncio import AsyncSession

from bot.db.models import AdminUser, Trade
from dashboard.api.auth.jwt import get_current_user
from dashboard.api.deps import get_db

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/monthly-pdf")
async def get_monthly_pdf(
    month: int = Query(default=0, description="Month offset (0=current, 1=last month, etc.)"),
    db: AsyncSession = Depends(get_db),
    _user: AdminUser = Depends(get_current_user),
):
    """Generate a monthly performance PDF report."""
    now = datetime.utcnow()
    # Calculate month range
    target = now.replace(day=1) - timedelta(days=30 * month)
    start = target.replace(day=1, hour=0, minute=0, second=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)

    # Fetch trades
    result = await db.execute(
        select(Trade)
        .where(Trade.closed_at >= start, Trade.closed_at < end, Trade.status == "CLOSED")
        .order_by(Trade.closed_at)
    )
    trades = list(result.scalars().all())

    # Strategy breakdown
    strat_result = await db.execute(
        select(
            Trade.strategy_name,
            sa_func.count(Trade.id).label("cnt"),
            sa_func.sum(Trade.profit).label("pnl"),
            sa_func.count(Trade.id).filter(Trade.profit > 0).label("wins"),
        )
        .where(Trade.closed_at >= start, Trade.closed_at < end, Trade.status == "CLOSED")
        .group_by(Trade.strategy_name)
    )
    strategies = strat_result.all()

    # Daily P&L
    daily_result = await db.execute(
        select(
            cast(Trade.closed_at, Date).label("day"),
            sa_func.sum(Trade.profit).label("pnl"),
        )
        .where(Trade.closed_at >= start, Trade.closed_at < end, Trade.status == "CLOSED")
        .group_by(cast(Trade.closed_at, Date))
        .order_by(cast(Trade.closed_at, Date))
    )
    daily_data = daily_result.all()

    # Build PDF using basic reportlab-free approach (HTML-to-text table format)
    # Since we don't want to add heavy deps, generate a clean CSV-like PDF using simple bytes
    pdf_bytes = _generate_pdf_report(
        month_label=start.strftime("%B %Y"),
        trades=trades,
        strategies=strategies,
        daily_data=daily_data,
    )

    filename = f"altior_report_{start.strftime('%Y_%m')}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _generate_pdf_report(month_label: str, trades, strategies, daily_data) -> bytes:
    """Generate a simple PDF report using fpdf2 (lightweight, no system deps)."""
    try:
        from fpdf import FPDF
    except ImportError:
        # Fallback: return a text-based pseudo-PDF
        return _generate_text_report(month_label, trades, strategies, daily_data)

    pdf = FPDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # Header
    pdf.set_font("Helvetica", "B", 20)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 15, "Altior Holding", ln=True, align="C")
    pdf.set_font("Helvetica", "", 12)
    pdf.set_text_color(100, 100, 100)
    pdf.cell(0, 8, f"Rapport Mensuel - {month_label}", ln=True, align="C")
    pdf.ln(10)

    # Summary
    total_pnl = sum(float(t.profit or 0) for t in trades)
    winners = sum(1 for t in trades if (t.profit or 0) > 0)
    losers = len(trades) - winners
    win_rate = (winners / len(trades) * 100) if trades else 0
    best = max(trades, key=lambda t: t.profit or 0) if trades else None
    worst = min(trades, key=lambda t: t.profit or 0) if trades else None

    pdf.set_font("Helvetica", "B", 14)
    pdf.set_text_color(30, 30, 30)
    pdf.cell(0, 10, "Resume", ln=True)

    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(60, 60, 60)
    sign = "+" if total_pnl >= 0 else ""
    pdf.cell(0, 7, f"P&L Total: {sign}{total_pnl:.2f} EUR", ln=True)
    pdf.cell(0, 7, f"Trades: {len(trades)} ({winners}W / {losers}L)", ln=True)
    pdf.cell(0, 7, f"Win Rate: {win_rate:.1f}%", ln=True)
    if best:
        pdf.cell(0, 7, f"Meilleur trade: {best.epic} +{best.profit:.2f}", ln=True)
    if worst and (worst.profit or 0) < 0:
        pdf.cell(0, 7, f"Pire trade: {worst.epic} {worst.profit:.2f}", ln=True)
    pdf.ln(8)

    # Strategy breakdown
    if strategies:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 10, "Performance par Strategie", ln=True)

        # Table header
        pdf.set_font("Helvetica", "B", 10)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(60, 8, "Strategie", border=1, fill=True)
        pdf.cell(25, 8, "Trades", border=1, fill=True, align="C")
        pdf.cell(30, 8, "Win Rate", border=1, fill=True, align="C")
        pdf.cell(35, 8, "P&L", border=1, fill=True, align="C")
        pdf.ln()

        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(60, 60, 60)
        for s in strategies:
            pnl = float(s.pnl or 0)
            wr = s.wins / s.cnt * 100 if s.cnt else 0
            name = (s.strategy_name or "").replace("ap_", "")[:25]
            pdf.cell(60, 7, name, border=1)
            pdf.cell(25, 7, str(s.cnt), border=1, align="C")
            pdf.cell(30, 7, f"{wr:.1f}%", border=1, align="C")
            sign = "+" if pnl >= 0 else ""
            pdf.cell(35, 7, f"{sign}{pnl:.2f}", border=1, align="C")
            pdf.ln()
        pdf.ln(8)

    # Trade list
    if trades:
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_text_color(30, 30, 30)
        pdf.cell(0, 10, "Detail des Trades", ln=True)

        pdf.set_font("Helvetica", "B", 9)
        pdf.set_fill_color(240, 240, 240)
        pdf.cell(30, 7, "Date", border=1, fill=True)
        pdf.cell(45, 7, "Epic", border=1, fill=True)
        pdf.cell(20, 7, "Dir", border=1, fill=True, align="C")
        pdf.cell(20, 7, "Size", border=1, fill=True, align="C")
        pdf.cell(30, 7, "P&L", border=1, fill=True, align="C")
        pdf.cell(35, 7, "Strategie", border=1, fill=True)
        pdf.ln()

        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(60, 60, 60)
        for t in trades[-50:]:  # Last 50
            date_str = t.closed_at.strftime("%d/%m %H:%M") if t.closed_at else ""
            pnl = float(t.profit or 0)
            sign = "+" if pnl >= 0 else ""
            strat = (t.strategy_name or "")[:15]
            pdf.cell(30, 6, date_str, border=1)
            pdf.cell(45, 6, (t.epic or "")[:20], border=1)
            pdf.cell(20, 6, t.direction or "", border=1, align="C")
            pdf.cell(20, 6, f"{t.size:.1f}", border=1, align="C")
            pdf.cell(30, 6, f"{sign}{pnl:.2f}", border=1, align="C")
            pdf.cell(35, 6, strat, border=1)
            pdf.ln()

    # Footer
    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(150, 150, 150)
    pdf.cell(0, 5, f"Genere le {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC - Altior Holding Auto-Trade IG", ln=True, align="C")

    return pdf.output()


def _generate_text_report(month_label: str, trades, strategies, daily_data) -> bytes:
    """Fallback text report when fpdf2 is not installed."""
    lines = [
        "ALTIOR HOLDING - Rapport Mensuel",
        f"Periode: {month_label}",
        "=" * 50,
        "",
    ]
    total_pnl = sum(float(t.profit or 0) for t in trades)
    winners = sum(1 for t in trades if (t.profit or 0) > 0)
    win_rate = (winners / len(trades) * 100) if trades else 0
    lines.append(f"P&L Total: {'+' if total_pnl >= 0 else ''}{total_pnl:.2f} EUR")
    lines.append(f"Trades: {len(trades)} ({winners}W / {len(trades) - winners}L)")
    lines.append(f"Win Rate: {win_rate:.1f}%")
    lines.append("")

    for t in trades[:30]:
        pnl = float(t.profit or 0)
        lines.append(f"  {t.epic:20s} {t.direction:4s} {'+' if pnl >= 0 else ''}{pnl:.2f}")

    return "\n".join(lines).encode("utf-8")
