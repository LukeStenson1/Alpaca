"""Influencer suggestion engine.

Scans configured YouTube channels, uses the Emergent LLM key to extract stock
ideas (ticker + bull/bear thesis + conviction) from each video's title and
description, then surfaces them as 'ideas' and auto-adds bullish, Alpaca-valid
tickers to the watchlist (low conviction; repeated mentions raise conviction,
which can eventually clear the auto-buy gate).
"""
import os
import re
import json
import logging
from datetime import datetime, timezone, timedelta

from emergentintegrations.llm.chat import LlmChat, UserMessage

import youtube_service
from alpaca_service import get_service
from models import (
    InfluencerChannel, InfluencerIdea, Watchlist, Parameters, SystemState,
)

logger = logging.getLogger("influencers")

LLM_MODEL = ("openai", "gpt-5.4")

DEFAULT_CHANNELS = [
    {"query": "Jeremy Lefebvre Financial Education", "name": "Jeremy Lefebvre"},
    {"query": "BWB Business With Brian", "name": "BWB - Brian"},
]

SYSTEM_MSG = (
    "You are an equity research analyst. You read a YouTube investing video's "
    "title and description and extract the specific US-listed stocks the creator "
    "discusses as investment ideas. Return ONLY valid JSON: a list of objects with "
    "keys: ticker (string, US exchange symbol), company (string), signal "
    "('bull' | 'bear' | 'neutral'), conviction (integer 1-5 reflecting how strongly "
    "the creator endorses it), thesis (one or two sentence summary of their reasoning). "
    "Only include real, explicitly-mentioned stock tickers. Ignore crypto, indices, "
    "and generic market commentary. If there are no concrete stock ideas, return []."
)


def utcnow():
    return datetime.now(timezone.utc)


def keys_configured():
    return bool(os.environ.get("YOUTUBE_API_KEY")) and bool(os.environ.get("EMERGENT_LLM_KEY"))


def seed_default_channels(db):
    if db.query(InfluencerChannel).count() == 0:
        for c in DEFAULT_CHANNELS:
            db.add(InfluencerChannel(query=c["query"], name=c["name"], active=True,
                                     created_at=utcnow()))
        db.commit()


def _parse_json(text):
    if not text:
        return []
    t = text.strip()
    t = re.sub(r"^```(?:json)?", "", t).strip()
    t = re.sub(r"```$", "", t).strip()
    try:
        data = json.loads(t)
    except Exception:
        m = re.search(r"\[.*\]", t, re.S)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except Exception:
            return []
    return data if isinstance(data, list) else []


async def _extract_ideas(video):
    chat = LlmChat(
        api_key=os.environ.get("EMERGENT_LLM_KEY"),
        session_id=f"inf-{video['video_id']}",
        system_message=SYSTEM_MSG,
    ).with_model(*LLM_MODEL)
    prompt = (
        f"Channel: {video.get('channel_title')}\n"
        f"Title: {video.get('title')}\n"
        f"Description:\n{(video.get('description') or '')[:4000]}\n\n"
        "Extract the stock ideas as a JSON list."
    )
    try:
        resp = await chat.send_message(UserMessage(text=prompt))
    except Exception as e:
        logger.warning("LLM extraction failed for %s: %s", video["video_id"], e)
        return []
    return _parse_json(resp if isinstance(resp, str) else getattr(resp, "content", ""))


def _persist_idea(db, svc, ch, video, idea, summary):
    ticker = (idea.get("ticker") or "").strip().upper()
    if not ticker or not re.match(r"^[A-Z][A-Z.\-]{0,5}$", ticker):
        return False
    if db.query(InfluencerIdea).filter_by(video_id=video["video_id"], ticker=ticker).first():
        return False

    signal = (idea.get("signal") or "neutral").lower()
    try:
        conviction = max(1, min(5, int(idea.get("conviction") or 3)))
    except Exception:
        conviction = 3
    thesis = (idea.get("thesis") or "").strip()
    company = (idea.get("company") or "").strip() or None

    # validate ticker against Alpaca
    valid = False
    asset_name = company
    try:
        asset = svc.get_asset(ticker)
        valid = bool(asset.get("tradable"))
        asset_name = asset.get("name") or company
    except Exception:
        valid = False

    action = "advisory"
    if signal == "bull" and valid:
        w = db.query(Watchlist).get(ticker)
        if not w:
            db.add(Watchlist(ticker=ticker, name=asset_name, active=True, date_added=utcnow(),
                             conviction=2, thesis=thesis,
                             notes=f"Auto-added from {ch.name} (YouTube)"))
            db.add(Parameters(ticker=ticker))
            action = "added"
            summary["watchlist_added"] += 1
        else:
            new_conv = min(5, (w.conviction or 2) + 1)
            if new_conv != (w.conviction or 2):
                w.conviction = new_conv
            if not w.thesis and thesis:
                w.thesis = thesis
            action = "updated"
            summary["watchlist_updated"] += 1

    rec = InfluencerIdea(
        channel_name=ch.name, video_id=video["video_id"], video_title=video["title"],
        video_url=f"https://www.youtube.com/watch?v={video['video_id']}",
        published_at=video.get("published_at"), ticker=ticker, company=asset_name,
        signal=signal, conviction=conviction, thesis=thesis, action=action,
        status="pending", created_at=utcnow(),
    )
    db.add(rec)
    db.flush()
    summary["ideas_created"] += 1
    return True


async def scan_all(db, max_videos=4, days=45):
    if not keys_configured():
        raise RuntimeError("YOUTUBE_API_KEY and EMERGENT_LLM_KEY must be configured")
    state = db.query(SystemState).get(1)
    svc = get_service(state.trading_mode if state else "paper")
    published_after = (utcnow() - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")

    summary = {"scanned_videos": 0, "ideas_created": 0,
               "watchlist_added": 0, "watchlist_updated": 0, "channels": []}

    channels = db.query(InfluencerChannel).filter(InfluencerChannel.active == True).all()  # noqa: E712
    for ch in channels:
        if not ch.channel_id:
            resolved = youtube_service.resolve_channel(ch.query)
            if not resolved:
                summary["channels"].append({"name": ch.name, "error": "channel not found"})
                continue
            ch.channel_id = resolved["channel_id"]
            if not ch.name:
                ch.name = resolved["name"]
            db.commit()
        try:
            videos = youtube_service.recent_videos(ch.channel_id, max_videos, published_after)
            if videos:
                details = youtube_service.video_details([v["video_id"] for v in videos])
                for v in videos:
                    v["description"] = details.get(v["video_id"], v["description"])
        except Exception as e:
            summary["channels"].append({"name": ch.name, "error": str(e)})
            continue

        ch_ideas = 0
        for v in videos:
            summary["scanned_videos"] += 1
            for idea in await _extract_ideas(v):
                if _persist_idea(db, svc, ch, v, idea, summary):
                    ch_ideas += 1
        ch.last_scanned_at = utcnow()
        db.commit()
        summary["channels"].append({"name": ch.name, "videos": len(videos), "ideas": ch_ideas})

    return summary
