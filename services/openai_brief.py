"""Market brief grounded in live terminal data only.

When OpenAI is configured and has quota, the evidence JSON below is sent to the
model for a narrative. When OpenAI is missing, exhausted or otherwise failing,
the same evidence is summarised by a transparent local engine and the response
is clearly labelled as a local fallback. Nothing is invented: prices, levels,
model output and momentum notes all come from the live Yahoo candles, genuine
RandomForest prediction and ATR(14) calculation used by Target & Stoploss.
No orders are placed and no outcome is guaranteed.
"""

import asyncio
import json
import time
from typing import Any, Dict, Optional, Tuple

from ai.ml_model import ml
from config.settings import settings
from config.symbols import market_catalog
from core.logger import logger
from services.target_planner import FALLBACK_INTERVAL, INTERVAL, _build_row
from services.yahoo_client import yahoo

SYSTEM_PROMPT = """You are a market research writer for a live Indian equities terminal.
Use ONLY the evidence JSON supplied by the user. Never invent prices, news, dates,
volumes or events, and never state or imply guaranteed profit. Do not tell the user
to place an order. Separate observed data from interpretation and be explicit about
uncertainty. If the signal is WAIT, say so plainly in the summary. Keep the whole
answer under 170 words, in plain English with no markdown and no bullet symbols.
Return strict JSON only, with exactly these keys:
- summary: one or two sentences
- observations: array of at most 3 short factual strings
- risks: array of at most 2 short strings
- watch_conditions: array of at most 3 short strings describing what to re-check
"""

_CACHE: Dict[Tuple[str, str], Tuple[float, Dict[str, Any]]] = {}
_LOCK = asyncio.Lock()

DISCLAIMER = (
    "AI-generated research from live Yahoo data and the terminal's RandomForest model. "
    "Not financial advice; nothing here places an order or guarantees an outcome."
)
LOCAL_DISCLAIMER = (
    "Grounded local research from live Yahoo data and the terminal models, shown because "
    "OpenAI was unavailable. Not financial advice; nothing here places an order or "
    "guarantees an outcome."
)


class BriefUnavailable(Exception):
    """Raised when a brief cannot be produced from real data."""

    def __init__(self, message: str, code: Optional[str] = None) -> None:
        super().__init__(message)
        self.code = code


def brief_status() -> Dict[str, Any]:
    """Expose configuration state without ever revealing the API key."""
    return {
        "provider": "OpenAI with grounded local fallback",
        "configured": settings.openai_configured,
        "model": settings.OPENAI_MODEL,
        "cache_ttl_seconds": settings.OPENAI_BRIEF_TTL_SECONDS,
        "fallback_enabled": True,
        "note": (
            "OpenAI narrative when available; otherwise a clearly labelled local summary "
            "from the same live Yahoo candles, RandomForest output and ATR levels. "
            "No orders, no fabricated data, no guaranteed-profit claims."
        ),
    }


def _display_name(symbol: str) -> str:
    catalog = market_catalog()
    for group in ("indices", "banks", "nse_companies", "bse_companies"):
        for item in catalog[group]:
            if item["symbol"] == symbol:
                return item.get("name") or symbol
    return symbol


def _evidence(row: Dict[str, Any], requested_interval: str) -> Dict[str, Any]:
    """Only values derived from real live data are sent to the model."""
    return {
        "symbol": row["symbol"],
        "company": row["name"],
        "exchange": row["exchange"],
        "data_interval": row["interval_used"],
        "requested_interval": requested_interval,
        "market_time_ist": row["market_time"],
        "last_price": row["price"],
        "change_pct": row["change_pct"],
        "terminal_signal": row["signal"],
        "terminal_confidence_pct": row["confidence"],
        "reference_only": row["reference_only"],
        "stale": row["stale"],
        "random_forest": {
            "bias": row["ml_bias"],
            "confidence_pct": row["ml_confidence"],
            "out_of_sample_accuracy_pct": row["model_accuracy"],
        },
        "momentum": {
            "score": row["momentum_score"],
            "side": row["momentum_side"],
            "ema20": row["ema20"],
            "ema50": row["ema50"],
            "rsi_value": row["rsi14"],
            "notes": row["reason"].split(" • ")[:6],
        },
        "atr_derived_levels": {
            "entry": row["entry"],
            "watch_zone_low": row["zone_low"],
            "watch_zone_high": row["zone_high"],
            "target": row["target"],
            "stoploss": row["stoploss"],
            "risk_reward": row["risk_reward"],
        },
        "horizon": row["horizon"],
        "data_source": row["source"],
        "delay_note": "Yahoo Finance NSE quotes may be delayed about 15 minutes",
    }


def _num(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{value:,.2f}"
    return "—"


def _local_brief(evidence: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic narrative built only from the evidence values above."""
    rf = evidence["random_forest"]
    mom = evidence["momentum"]
    lv = evidence["atr_derived_levels"]
    signal = evidence["terminal_signal"]

    if evidence["stale"] or evidence["reference_only"]:
        stance = (
            "The terminal marks this row reference-only, so the levels are context "
            "rather than an actionable setup."
        )
    elif signal == "WAIT":
        stance = (
            "The terminal signal is WAIT: RandomForest and momentum do not align "
            "strongly enough in this snapshot."
        )
    elif signal == "BUY":
        stance = (
            "The terminal signal is BUY, but that is a model-derived view, not a "
            "forecast or an instruction to trade."
        )
    else:
        stance = (
            "The terminal signal is SELL, but that is a model-derived view, not a "
            "forecast or an instruction to trade."
        )

    market_time = str(evidence["market_time_ist"] or "—")
    time_suffix = "" if ("+" in market_time or market_time.endswith("Z")) else " IST"
    summary = (
        f"{evidence['company']} ({evidence['symbol']}) was last observed at "
        f"₹{_num(evidence['last_price'])} ({evidence['change_pct']:+.2f}%) on "
        f"{evidence['data_interval']} data timed {market_time}{time_suffix}. "
        f"{stance}"
    )

    observations = [
        (
            f"Terminal signal {signal} at {evidence['terminal_confidence_pct']}% confidence; "
            f"RandomForest bias {rf['bias']} at {rf['confidence_pct']}% class probability."
        ),
        (
            f"ATR(14) levels from the same candles: entry ₹{_num(lv['entry'])}, "
            f"target ₹{_num(lv['target'])}, stoploss ₹{_num(lv['stoploss'])} "
            f"(1:{lv['risk_reward']})."
        ),
        (
            f"Momentum side {mom['side']}, score {mom['score']}, EMA20 ₹{_num(mom['ema20'])}, "
            f"EMA50 ₹{_num(mom['ema50'])}, RSI value {mom['rsi_value'] if mom['rsi_value'] is not None else '—'}."
        ),
    ]

    risks = [
        (
            f"RandomForest out-of-sample accuracy is {rf['out_of_sample_accuracy_pct']}% "
            "(near a coin-flip baseline); class probability is not a calibrated success rate."
        ),
        (
            "Yahoo NSE quotes may be delayed about 15 minutes; levels can change on the "
            "next completed candle."
        ),
    ]
    if evidence["stale"]:
        risks.append("The latest Yahoo candle is stale; this row is reference-only.")

    watch_conditions = [
        (
            f"Recheck price against the ATR watch zone ₹{_num(lv['watch_zone_low'])}–"
            f"₹{_num(lv['watch_zone_high'])} before drawing any conclusion."
        ),
        (
            f"Recheck RandomForest bias and momentum agreement after the next completed "
            f"{evidence['data_interval']} candle ({evidence['horizon']})."
        ),
        "Generate a fresh brief instead of relying on a cached card.",
    ]

    return {
        "summary": summary[:800],
        "observations": [item[:300] for item in observations[:3]],
        "risks": [item[:300] for item in risks[:2]],
        "watch_conditions": [item[:300] for item in watch_conditions[:3]],
    }


def _clean_section(value: Any, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip()[:300] for item in value[:limit] if str(item).strip()]


def _parse_reply(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith("json"):
            text = text[4:].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise BriefUnavailable(
            "OpenAI returned an unreadable response", "openai_parse_error"
        ) from exc
    if not isinstance(payload, dict) or not str(payload.get("summary", "")).strip():
        raise BriefUnavailable(
            "OpenAI returned an incomplete response", "openai_incomplete"
        )
    return {
        "summary": str(payload["summary"]).strip()[:800],
        "observations": _clean_section(payload.get("observations"), 3),
        "risks": _clean_section(payload.get("risks"), 2),
        "watch_conditions": _clean_section(payload.get("watch_conditions"), 3),
    }


async def _ask_openai(evidence: Dict[str, Any]) -> Dict[str, Any]:
    if not settings.openai_configured:
        raise BriefUnavailable(
            "OPENAI_API_KEY is not configured on the server", "openai_not_configured"
        )
    try:
        from openai import AsyncOpenAI
    except ImportError as exc:
        raise BriefUnavailable(
            "OpenAI client library is not installed on the server", "openai_missing"
        ) from exc

    client = AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,
        timeout=max(20.0, settings.REQUEST_TIMEOUT_SECONDS * 3),
        max_retries=1,
    )
    try:
        response = await client.chat.completions.create(
            model=settings.OPENAI_MODEL,
            temperature=0.2,
            max_tokens=450,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)},
            ],
        )
    except Exception as exc:
        # Log the class/code only; API payloads can echo request details.
        code = str(getattr(exc, "code", None) or getattr(exc, "status_code", None) or "")
        logger.warning(
            f"OpenAI brief failed ({exc.__class__.__name__}, code={code or 'none'}); "
            "using grounded local fallback"
        )
        raise BriefUnavailable(
            f"OpenAI request failed{f' ({code})' if code else ''}", code or "openai_error"
        ) from exc
    finally:
        await client.close()

    content = response.choices[0].message.content if response.choices else ""
    return _parse_reply(content or "")


async def generate_brief(
    symbol: str = "RELIANCE", interval: str = INTERVAL, refresh: bool = False
) -> Dict[str, Any]:
    """Build a grounded brief for one live symbol, with an honest local fallback."""
    if interval not in (INTERVAL, FALLBACK_INTERVAL):
        raise BriefUnavailable("Briefs support 5m and 1d intervals.", "bad_interval")

    normalized = yahoo.normalize_symbol(symbol)
    key = (normalized, interval)
    cached = _CACHE.get(key)
    if not refresh and cached and time.monotonic() - cached[0] < settings.OPENAI_BRIEF_TTL_SECONDS:
        return {**cached[1], "meta": {**cached[1]["meta"], "cache": "hit"}}

    async with _LOCK:
        cached = _CACHE.get(key)
        if not refresh and cached and time.monotonic() - cached[0] < settings.OPENAI_BRIEF_TTL_SECONDS:
            return {**cached[1], "meta": {**cached[1]["meta"], "cache": "hit"}}

        bundle = await ml.bundle(INTERVAL)
        item = {
            "symbol": normalized,
            "name": _display_name(normalized),
            "group": "brief",
            "group_label": "AI Brief",
        }
        last_error: Optional[Exception] = None
        row: Optional[Dict[str, Any]] = None
        used_interval = interval
        for candidate in (interval, FALLBACK_INTERVAL) if interval == INTERVAL else (interval,):
            try:
                data = await yahoo.chart(normalized, candidate, 200)
                row = _build_row(item, data, bundle, candidate)
                used_interval = candidate
                break
            except Exception as exc:
                last_error = exc
                if candidate == INTERVAL:
                    logger.warning(
                        f"AI brief {normalized}: 5m unavailable ({exc}); retrying 1d"
                    )
        if row is None:
            raise BriefUnavailable(
                f"Live Yahoo data is unavailable for {normalized}: {last_error}",
                "live_data_unavailable",
            )

        evidence = _evidence(row, interval)
        narrative: Optional[Dict[str, Any]] = None
        fallback_reason: Optional[str] = None
        fallback_code: Optional[str] = None

        if settings.openai_configured:
            try:
                narrative = await _ask_openai(evidence)
            except BriefUnavailable as exc:
                fallback_reason = str(exc)
                fallback_code = exc.code

        local = narrative is None
        if local:
            narrative = _local_brief(evidence)
            fallback_reason = fallback_reason or "OPENAI_API_KEY is not configured on the server"
            fallback_code = fallback_code or "openai_not_configured"

        payload = {
            "symbol": normalized,
            "name": row["name"],
            "interval_used": used_interval,
            "narrative": narrative,
            "evidence": evidence,
            "disclaimer": LOCAL_DISCLAIMER if local else DISCLAIMER,
            "meta": {
                "provider": "Local evidence engine" if local else "OpenAI",
                "model": "deterministic-from-live-evidence" if local else settings.OPENAI_MODEL,
                "fallback": local,
                "fallback_reason": fallback_reason,
                "fallback_code": fallback_code,
                "openai_configured": settings.openai_configured,
                "cache": "miss",
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "source": "Yahoo Finance live chart API + RandomForest + ATR(14)",
            },
        }
        _CACHE[key] = (time.monotonic(), payload)
        return payload
