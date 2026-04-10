"""
WaveForm Web – FastAPI application.

Endpoints:
  GET /                          → serves static/index.html
  GET /api/search?q=X            → returns up to 8 song suggestions (for dropdown)
  GET /api/graph?song=X          → returns D3 graph JSON (text search, uses first result)
  GET /api/graph?trackId=X       → returns D3 graph JSON for an exact iTunes trackId
  GET /api/youtube?artist=X&title=Y → returns YouTube videoId for music video (or null)
  GET /api/health                → {"status": "ok"}
"""

import asyncio
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

import httpx
import yt_dlp
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

import json
import sys
sys.path.insert(0, os.path.dirname(__file__))

# Persist YouTube video ID cache to disk so server restarts don't re-burn quota
_YT_CACHE_FILE = Path(__file__).parent.parent / ".yt_cache.json"

def _load_yt_cache() -> dict:
    try:
        return json.loads(_YT_CACHE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _save_yt_cache(cache: dict) -> None:
    try:
        _YT_CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
    except Exception:
        pass

_YT_CACHE: dict[str, str | None] = _load_yt_cache()

from itunes_client import search_song, search_by_artist, search_same_album, search_by_style, lookup_by_id, attach_genres
from graph_builder import build_graph

app = FastAPI(title="WaveForm Web")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Resolve the static directory relative to this file's location
_STATIC_DIR = Path(__file__).parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def index():
    """Serve the main single-page app."""
    html_path = _STATIC_DIR / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(str(html_path))


@app.get("/api/search")
async def search_suggestions(q: str = Query(..., min_length=1, description="Partial song or artist name")):
    """
    Return up to 8 song suggestions for the search dropdown.
    Each result includes title, artist, album, artworkUrl, and trackId.
    """
    results = await search_song(q, limit=8)
    suggestions = [
        {
            "trackId":    r["id"],
            "title":      r["title"],
            "artist":     r["artist"],
            "album":      r.get("album", ""),
            "genre":      r.get("raw_genre", r["genre"]),
            "artworkUrl": r.get("artworkUrl", ""),
            "previewUrl": r.get("previewUrl"),
        }
        for r in results
    ]
    return JSONResponse({"results": suggestions})


@app.get("/api/health")
async def health():
    return {"status": "ok"}


# Keywords that suggest the result is NOT a real music video
_NOT_MV = {"lyrics", "lyric", "audio", "visualizer", "cover", "karaoke",
           "reaction", "slowed", "reverb", "nightcore", "live at", "live in",
           "concert", "tour", "interview", "behind the scenes", "making of"}

_YDL_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "skip_download": True,
    "extract_flat": "in_playlist",
    "noplaylist": True,
}


def _is_real_mv(video_title: str, artist: str, title: str) -> bool:
    vt = video_title.lower()
    if artist.lower() not in vt and title.lower() not in vt:
        return False
    for kw in _NOT_MV:
        if kw in vt:
            return False
    return True


def _yt_search_sync(query: str, artist: str, title: str) -> str | None:
    """Run yt-dlp search synchronously — called in a thread pool."""
    import yt_dlp
    try:
        with yt_dlp.YoutubeDL(_YDL_OPTS) as ydl:
            result = ydl.extract_info(f"ytsearch5:{query}", download=False)
            entries = result.get("entries", []) if result else []
            for entry in entries:
                if not entry:
                    continue
                vtitle = entry.get("title") or ""
                vid    = entry.get("id") or entry.get("url", "")
                # Strip full URL down to ID if needed
                if "/" in vid:
                    vid = vid.split("v=")[-1].split("/")[-1]
                if vid and _is_real_mv(vtitle, artist, title):
                    return vid
    except Exception as e:
        import logging
        logging.getLogger("api").warning(f"yt-dlp search failed for '{query}': {e}")
    return None


@app.get("/api/youtube")
async def youtube_video(
    artist: str = Query(..., description="Artist name"),
    title:  str = Query(..., description="Song title"),
):
    """
    Return the YouTube videoId for a song's official music video, or null.
    Uses yt-dlp (no API key, no quota) to search YouTube directly.
    Tries "{artist} {title} official video" then "{artist} {title} music video".
    Filters out lyric/audio/cover/reaction videos.
    Results cached to disk so restarts don't re-search the same songs.
    """
    cache_key = f"{artist.lower()}||{title.lower()}"
    if cache_key in _YT_CACHE:
        return JSONResponse({"videoId": _YT_CACHE[cache_key]})

    queries = [
        f"{artist} {title} official video",
        f"{artist} {title} music video",
    ]

    from concurrent.futures import ThreadPoolExecutor
    video_id = None
    with ThreadPoolExecutor(max_workers=1) as executor:
        for query in queries:
            future = executor.submit(_yt_search_sync, query, artist, title)
            try:
                video_id = await asyncio.wait_for(
                    asyncio.wrap_future(future), timeout=15.0
                )
            except Exception:
                video_id = None
            if video_id:
                break

    _YT_CACHE[cache_key] = video_id
    _save_yt_cache(_YT_CACHE)
    return JSONResponse({"videoId": video_id})


@app.get("/api/graph")
async def graph(
    song: Optional[str]    = Query(None, description="Song name to search for"),
    trackId: Optional[str] = Query(None, description="Exact iTunes trackId (preferred over song)"),
):
    """
    Return a D3 force-graph of related tracks.

    Three pools of related songs are fetched in parallel:
      1. artist_match  – other songs by the same artist
      2. album_match   – other tracks on the same album (most sonically similar)
      3. style_match   – songs from artists in the same stylistic niche
                         (searched as "{artist} {genre}" — not plain genre popularity)
    """
    if not song and not trackId:
        raise HTTPException(status_code=422, detail="Provide 'song' or 'trackId'")

    # Step 1: find seed song
    if trackId:
        seed_results = await lookup_by_id(trackId)
    else:
        seed_results = await search_song(song, limit=1)

    if not seed_results:
        label = trackId or song
        raise HTTPException(status_code=404, detail=f"No song found matching '{label}'")

    seed = seed_results[0]

    # Step 2: 3-way parallel fetch using Deezer artist/album IDs
    artist_songs, album_songs, style_songs = await asyncio.gather(
        search_by_artist(seed["artist_id"], limit=25),
        search_same_album(seed["album_id"], seed["artist"], limit=20),
        search_by_style(seed["artist_id"], seed["raw_genre"], limit=25),
    )

    # Step 3: attach real genres to all songs (batch album lookups, cached)
    all_songs = [seed] + artist_songs + album_songs + style_songs
    await attach_genres(all_songs)

    # Step 4: build graph
    graph_data = build_graph(seed, artist_songs, album_songs, style_songs)

    return JSONResponse({
        "seed": {
            "id":         seed["id"],
            "label":      seed["title"],
            "artist":     seed["artist"],
            "genre":      seed.get("raw_genre", seed["genre"]),
            "album":      seed.get("album", ""),
            "previewUrl": seed.get("previewUrl"),
            "artworkUrl": seed.get("artworkUrl", ""),
            "artist_id":  seed.get("artist_id", ""),
            "album_id":   seed.get("album_id", ""),
        },
        "graph": graph_data,
    })
