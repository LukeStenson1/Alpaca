"""Thin YouTube Data API v3 wrapper: resolve channels + list recent videos."""
import os
from googleapiclient.discovery import build


def _api_key():
    key = os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise RuntimeError("YOUTUBE_API_KEY is not configured")
    return key


def _client():
    return build("youtube", "v3", developerKey=_api_key(), cache_discovery=False)


def resolve_channel(query):
    """Resolve a handle (@name) or free-text query to a channel id + title."""
    yt = _client()
    handle = query.strip().lstrip("@")
    # 1) try direct handle lookup
    try:
        resp = yt.channels().list(part="snippet", forHandle=handle).execute()
        items = resp.get("items", [])
        if items:
            return {"channel_id": items[0]["id"], "name": items[0]["snippet"]["title"]}
    except Exception:
        pass
    # 2) fall back to channel search
    resp = yt.search().list(part="snippet", q=query, type="channel", maxResults=1).execute()
    items = resp.get("items", [])
    if not items:
        return None
    return {"channel_id": items[0]["id"]["channelId"], "name": items[0]["snippet"]["title"]}


def recent_videos(channel_id, max_results=4, published_after=None):
    """Most recent uploads for a channel (snippet only — descriptions truncated)."""
    yt = _client()
    kwargs = dict(part="snippet", channelId=channel_id, type="video",
                  order="date", maxResults=max_results)
    if published_after:
        kwargs["publishedAfter"] = published_after
    resp = yt.search().list(**kwargs).execute()
    out = []
    for it in resp.get("items", []):
        vid = it["id"].get("videoId")
        if not vid:
            continue
        sn = it["snippet"]
        out.append({
            "video_id": vid,
            "title": sn.get("title", ""),
            "description": sn.get("description", ""),
            "published_at": sn.get("publishedAt"),
            "channel_title": sn.get("channelTitle"),
        })
    return out


def video_details(video_ids):
    """Full (untruncated) descriptions for a list of video ids -> {id: description}."""
    if not video_ids:
        return {}
    yt = _client()
    resp = yt.videos().list(part="snippet", id=",".join(video_ids)).execute()
    return {it["id"]: it["snippet"].get("description", "") for it in resp.get("items", [])}
