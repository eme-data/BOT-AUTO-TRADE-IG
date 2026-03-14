"""AI Analysis endpoints – view logs, trigger reviews, check status."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from bot.ai.analyzer import ClaudeAnalyzer
from bot.ai.models import AIAnalysisRequest, AnalysisMode
from bot.config import settings
from bot.db.models import AdminUser
from bot.db.repository import AIAnalysisRepository
from bot.db.session import async_session_factory
from dashboard.api.auth.jwt import get_current_user

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ── Status ─────────────────────────────────────────────

@router.get("/status")
async def ai_status(_user: AdminUser = Depends(get_current_user)):
    """Check if AI is configured and enabled."""
    return {
        "enabled": settings.ai.enabled,
        "configured": bool(settings.ai.api_key),
        "model": settings.ai.model,
        "modes": {
            "pre_trade": settings.ai.pre_trade_enabled,
            "market_review": settings.ai.market_review_enabled,
            "sentiment": settings.ai.sentiment_enabled,
            "post_trade": settings.ai.post_trade_enabled,
        },
    }


# ── Analysis logs ──────────────────────────────────────

@router.get("/logs")
async def get_logs(limit: int = 50, _user: AdminUser = Depends(get_current_user)):
    """Get recent AI analysis logs."""
    async with async_session_factory() as session:
        repo = AIAnalysisRepository(session)
        logs = await repo.get_recent(limit=limit)
        return [
            {
                "id": log.id,
                "epic": log.epic,
                "mode": log.mode,
                "verdict": log.verdict,
                "confidence": log.confidence,
                "reasoning": log.reasoning,
                "market_summary": log.market_summary,
                "risk_warnings": log.risk_warnings,
                "suggested_adjustments": log.suggested_adjustments,
                "signal_direction": log.signal_direction,
                "signal_strategy": log.signal_strategy,
                "model_used": log.model_used,
                "latency_ms": log.latency_ms,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]


@router.get("/logs/{epic}")
async def get_logs_by_epic(epic: str, limit: int = 20, _user: AdminUser = Depends(get_current_user)):
    """Get AI analysis logs for a specific market."""
    async with async_session_factory() as session:
        repo = AIAnalysisRepository(session)
        logs = await repo.get_by_epic(epic, limit=limit)
        return [
            {
                "id": log.id,
                "epic": log.epic,
                "mode": log.mode,
                "verdict": log.verdict,
                "confidence": log.confidence,
                "reasoning": log.reasoning,
                "market_summary": log.market_summary,
                "risk_warnings": log.risk_warnings,
                "signal_direction": log.signal_direction,
                "model_used": log.model_used,
                "latency_ms": log.latency_ms,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]


# ── Post-trade reviews ────────────────────────────────

@router.get("/post-trade-reviews")
async def get_post_trade_reviews(limit: int = 30, _user: AdminUser = Depends(get_current_user)):
    """Get recent post-trade AI reviews."""
    async with async_session_factory() as session:
        repo = AIAnalysisRepository(session)
        logs = await repo.get_by_mode("post_trade", limit=limit)
        return [
            {
                "id": log.id,
                "epic": log.epic,
                "mode": log.mode,
                "verdict": log.verdict,
                "confidence": log.confidence,
                "reasoning": log.reasoning,
                "signal_direction": log.signal_direction,
                "signal_strategy": log.signal_strategy,
                "score": (log.suggested_adjustments or {}).get("score"),
                "lessons_learned": (log.suggested_adjustments or {}).get("lessons_learned", []),
                "what_went_well": (log.suggested_adjustments or {}).get("what_went_well", []),
                "what_could_improve": (log.suggested_adjustments or {}).get("what_could_improve", []),
                "model_used": log.model_used,
                "latency_ms": log.latency_ms,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ]


# ── Stats ──────────────────────────────────────────────

@router.get("/stats")
async def get_stats(_user: AdminUser = Depends(get_current_user)):
    """Get AI analysis statistics."""
    async with async_session_factory() as session:
        repo = AIAnalysisRepository(session)
        return await repo.get_stats()


# ── Manual analysis trigger ────────────────────────────

class ManualAnalysisRequest(BaseModel):
    epic: str
    mode: str = "market_review"


@router.post("/analyze")
async def trigger_analysis(body: ManualAnalysisRequest, _user: AdminUser = Depends(get_current_user)):
    """Trigger a manual AI analysis for a market."""
    if not settings.ai.enabled or not settings.ai.api_key:
        return {"error": "AI non configure. Activez-le dans les parametres."}

    analyzer = ClaudeAnalyzer()

    try:
        from bot.broker.ig_rest import IGRestClient
        from bot.data.indicators import add_all_indicators
        import pandas as pd

        broker = IGRestClient()
        await broker.connect()

        try:
            bars = await broker.get_historical_prices(body.epic, "HOUR", 100)

            indicators: dict = {}
            recent_bars: list[dict] = []

            if bars:
                data = [{"time": b.time, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume} for b in bars]
                df = pd.DataFrame(data)
                if not df.empty:
                    df.set_index("time", inplace=True)
                    df.sort_index(inplace=True)
                    df = add_all_indicators(df)
                    last = df.iloc[-1]
                    for col in ["rsi", "macd", "macd_histogram", "atr", "adx", "ema_20", "ema_50", "ema_200"]:
                        if col in df.columns:
                            try:
                                indicators[col] = float(last[col])
                            except (TypeError, ValueError):
                                pass
                    for _, row in df.tail(10).iterrows():
                        recent_bars.append({
                            "open": float(row["open"]),
                            "high": float(row["high"]),
                            "low": float(row["low"]),
                            "close": float(row["close"]),
                            "volume": float(row["volume"]),
                        })

            mode = AnalysisMode(body.mode)
            request = AIAnalysisRequest(
                mode=mode,
                pair=body.epic,
                indicators=indicators,
                recent_bars=recent_bars,
            )

            result = await analyzer.analyze(request)

            # Persist
            async with async_session_factory() as session:
                ai_repo = AIAnalysisRepository(session)
                await ai_repo.save(
                    epic=body.epic,
                    mode=body.mode,
                    verdict=result.verdict.value,
                    confidence=result.confidence,
                    reasoning=result.reasoning,
                    market_summary=result.market_summary,
                    risk_warnings=result.risk_warnings,
                    suggested_adjustments=result.suggested_adjustments,
                    model_used=result.model_used,
                    latency_ms=result.latency_ms,
                )

            return {
                "verdict": result.verdict.value,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
                "market_summary": result.market_summary,
                "risk_warnings": result.risk_warnings,
                "suggested_adjustments": result.suggested_adjustments,
                "model": result.model_used,
                "latency_ms": result.latency_ms,
            }
        finally:
            await broker.disconnect()
    except Exception as exc:
        return {"error": str(exc)}
    finally:
        await analyzer.close()
