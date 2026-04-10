"""
Deezer API client for WaveForm Web.

Uses the Deezer public API (no API key required).
Replaces the iTunes client for better catalogue coverage and real similarity
via Deezer's own related-artists endpoint.

Key differences vs iTunes:
  - search_song / lookup_by_id keep the same call signatures used by api.py
  - Artist/album/style lookups now use Deezer IDs, not text queries
  - get_related_artist_tracks() uses Deezer's actual similarity graph
"""

import asyncio
import httpx

_BASE = "https://api.deezer.com"
_cache: dict[str, object] = {}

# Persistent clients — reuses TCP/SSL connections instead of handshaking each call
_deezer_client: httpx.AsyncClient | None = None
_itunes_client_http: httpx.AsyncClient | None = None


def _get_deezer_client() -> httpx.AsyncClient:
    global _deezer_client
    if _deezer_client is None or _deezer_client.is_closed:
        _deezer_client = httpx.AsyncClient(timeout=10.0)
    return _deezer_client


def _get_itunes_client() -> httpx.AsyncClient:
    global _itunes_client_http
    if _itunes_client_http is None or _itunes_client_http.is_closed:
        _itunes_client_http = httpx.AsyncClient(timeout=8.0)
    return _itunes_client_http


# ─── Low-level helpers ────────────────────────────────────────────────────────

async def _get(path: str, params: dict | None = None) -> dict:
    cache_key = path + str(sorted((params or {}).items()))
    if cache_key in _cache:
        return _cache[cache_key]
    client = _get_deezer_client()
    resp = await client.get(_BASE + path, params=params)
    resp.raise_for_status()
    data = resp.json()
    _cache[cache_key] = data
    return data


async def _search(q: str, limit: int = 10) -> list[dict]:
    data = await _get("/search", {"q": q, "limit": limit})
    return [normalize(t) for t in data.get("data", [])]


# Deezer genre_id → display name (from /genre endpoint)
_DEEZER_GENRE_IDS: dict[int, str] = {
    0: "Music", 132: "Pop", 116: "Rap/Hip Hop", 122: "Reggaeton",
    152: "Rock", 113: "Dance", 165: "R&B", 85: "Alternative",
    186: "Christian", 106: "Electronic", 466: "Folk", 144: "Reggae",
    129: "Jazz", 84: "Country", 67: "Salsa", 65: "Traditional Mexicano",
    98: "Classical", 173: "Films/Games", 464: "Metal", 169: "Soul & Funk",
    2: "African Music", 16: "Asian Music", 153: "Blues",
    75: "Brazilian Music", 71: "Cumbia", 81: "Indian Music",
    95: "Kids", 197: "Latin Music",
}

# Label substrings that hint at regional genre when Deezer has no genre_id
_LABEL_HINTS: list[tuple[str, str]] = [
    ("taiwan", "Asian Music"), ("hong kong", "Asian Music"),
    ("china", "Asian Music"), ("japan", "Asian Music"),
    ("korea", "Asian Music"), ("jvr", "Asian Music"),
    ("sm entertainment", "Asian Music"), ("big hit", "Asian Music"),
    ("avex", "Asian Music"), ("pony canyon", "Asian Music"),
    ("latin", "Latin Music"), ("reggaeton", "Latin Music"),
    ("universal music india", "Indian Music"),
    ("bollywood", "Indian Music"),
    ("africa", "African Music"),
    ("afrobeats", "African Music"),
]


async def get_album_genre(album_id: str) -> str:
    """
    Fetch the primary genre name for a Deezer album using a 3-tier fallback:
      1. genres.data array (most accurate)
      2. genre_id integer field mapped to Deezer's genre list
      3. Label name substring hints for regional music
    Returns "Music" as the final fallback (never "Unknown").
    """
    if not album_id or album_id == "0":
        return "Music"
    data = await _get(f"/album/{album_id}")

    # Tier 1: genres array
    genres = data.get("genres", {}).get("data", [])
    if genres:
        return genres[0]["name"]

    # Tier 2: genre_id integer
    genre_id = data.get("genre_id", -1)
    if genre_id and genre_id != -1 and genre_id in _DEEZER_GENRE_IDS:
        return _DEEZER_GENRE_IDS[genre_id]

    # Tier 3: label name hints
    label = (data.get("label") or "").lower()
    for substr, genre_name in _LABEL_HINTS:
        if substr in label:
            return genre_name

    return "Music"


_itunes_cache: dict[str, str] = {}
_ITUNES_SEARCH = "https://itunes.apple.com/search"


async def get_itunes_genre(artist_name: str, title_hint: str = "") -> str:
    """
    Query the iTunes Search API for the most common primaryGenreName for an artist.

    If title_hint is provided, searches "{artist} {title}" without the artistTerm
    attribute restriction, then only counts genres from results where artistName
    case-insensitively matches — prevents ambiguous names like "MIKE" or "Jay" from
    picking up genres from unrelated artists with the same name.

    Falls back to artist-only search if the hint search yields no matching results.
    Returns the genre string, or "" if nothing found.
    Results cached by lowercased artist name.
    """
    from collections import Counter

    key = artist_name.lower().strip()
    if key in _itunes_cache:
        return _itunes_cache[key]

    artist_lower = artist_name.lower().strip()

    async def _search_itunes(term: str, attribute: str | None) -> list[dict]:
        params = {"term": term, "entity": "song", "limit": 10}
        if attribute:
            params["attribute"] = attribute
        try:
            client = _get_itunes_client()
            resp = await client.get(_ITUNES_SEARCH, params=params)
            resp.raise_for_status()
            return resp.json().get("results", [])
        except Exception:
            return []

    # Pass 1: title-anchored search — filters by matching artistName to avoid
    # false hits on common names (MIKE, Jay, Chris, etc.)
    if title_hint:
        results = await _search_itunes(f"{artist_name} {title_hint}", None)
        matched = [
            r for r in results
            if r.get("artistName", "").lower().strip() == artist_lower
            and r.get("primaryGenreName")
        ]
        if matched:
            genre = Counter(r["primaryGenreName"] for r in matched).most_common(1)[0][0]
            _itunes_cache[key] = genre
            return genre

    # Pass 2: artist-term search — broader, no title disambiguation
    results = await _search_itunes(artist_name, "artistTerm")
    genre_counts = Counter(
        r["primaryGenreName"] for r in results if r.get("primaryGenreName")
    )
    genre = genre_counts.most_common(1)[0][0] if genre_counts else ""
    _itunes_cache[key] = genre
    return genre


async def attach_genres(songs: list[dict]) -> None:
    """
    Mutate each song dict in-place with accurate genre data via three layers.

    Layer 1 – iTunes artist genre (fast, specific, runs first for ALL artists):
      One call per unique artist. Specific genres (K-Pop, Mandopop, Reggaeton,
      Cantopop/HK-Pop, etc.) are applied immediately and those artists skip
      all further lookups — saving the bulk of Deezer album calls.

    Layer 2 – Deezer album genre (fallback for artists iTunes was generic on):
      Only fetches album objects for songs whose artist got a generic/missing
      iTunes result. This is the expensive layer, now only runs when needed.

    Layer 3 – MusicBrainz (subgenre precision for generic iTunes results):
      Queries MB for remaining artists with generic labels to find specific
      subgenres (e.g. "Experimental Hip Hop", "French House", "Electropop").
    """
    from musicbrainz_client import get_artist_genre, ITUNES_GENERIC

    unique_artists = list({s["artist"] for s in songs if s.get("artist")})
    if not unique_artists:
        return

    # Build a title hint per artist — one representative track title to help
    # iTunes disambiguate common names like "MIKE", "Jay", "Chris", etc.
    artist_title_hint: dict[str, str] = {}
    for s in songs:
        a = s.get("artist", "")
        if a and a not in artist_title_hint and s.get("title"):
            artist_title_hint[a] = s["title"]

    # ── Layer 1: iTunes for all unique artists (parallel, cached) ─────────────
    itunes_results = await asyncio.gather(*[
        get_itunes_genre(a, artist_title_hint.get(a, "")) for a in unique_artists
    ])
    itunes_map: dict[str, str] = dict(zip(unique_artists, itunes_results))

    needs_fallback: set[str] = set()
    for artist, itunes_genre in itunes_map.items():
        if itunes_genre and itunes_genre not in ITUNES_GENERIC:
            for song in songs:
                if song.get("artist") == artist:
                    song["raw_genre"] = itunes_genre
                    song["genre"]     = itunes_genre
        else:
            needs_fallback.add(artist)

    if not needs_fallback:
        return

    # ── Layer 2: Deezer album genres — only for fallback artists ─────────────
    fallback_songs = [s for s in songs if s.get("artist") in needs_fallback]
    album_ids = {
        s["album_id"] for s in fallback_songs
        if s.get("album_id") and s["album_id"] != "0"
    }
    if album_ids:
        deezer_results = await asyncio.gather(*[get_album_genre(aid) for aid in album_ids])
        deezer_map: dict[str, str] = dict(zip(album_ids, deezer_results))
        for song in fallback_songs:
            aid = song.get("album_id", "0")
            if aid in deezer_map:
                song["raw_genre"] = deezer_map[aid]
                song["genre"]     = deezer_map[aid]

    # ── Layer 3: MusicBrainz for subgenre precision ───────────────────────────
    mb_artists = list(needs_fallback)
    mb_results = await asyncio.gather(*[
        get_artist_genre(a, artist_title_hint.get(a, "")) for a in mb_artists
    ])
    mb_map: dict[str, str] = {
        artist: genre
        for artist, genre in zip(mb_artists, mb_results)
        if genre
    }

    for song in songs:
        mb_genre = mb_map.get(song.get("artist", ""))
        if mb_genre:
            song["raw_genre"] = mb_genre
            song["genre"]     = mb_genre


# ─── Public API (same signatures as itunes_client.py) ─────────────────────────

async def search_song(term: str, limit: int = 1) -> list[dict]:
    """Search Deezer by song/artist name. Returns normalised track dicts."""
    return await _search(term, limit=limit)


async def lookup_by_id(track_id: str) -> list[dict]:
    """Fetch a single track by its Deezer track ID."""
    data = await _get(f"/track/{track_id}")
    if "error" in data:
        return []
    return [normalize(data)]


async def search_by_artist(artist_id: str, limit: int = 25) -> list[dict]:
    """Top tracks by a specific artist (using Deezer artist ID)."""
    data = await _get(f"/artist/{artist_id}/top", {"limit": limit})
    return [normalize(t) for t in data.get("data", [])]


async def search_same_album(album_id: str, artist: str = "", limit: int = 20) -> list[dict]:
    """All tracks from the same album (using Deezer album ID)."""
    if not album_id or album_id == "0":
        return []
    data = await _get(f"/album/{album_id}/tracks", {"limit": limit})
    # Album track objects are minimal; patch in artist name from parent call
    tracks = []
    for t in data.get("data", []):
        if "artist" not in t or not t["artist"].get("name"):
            t.setdefault("artist", {})["name"] = artist
        # Album track objects don't include cover; fetch from album
        t.setdefault("album", {})["id"] = album_id
        tracks.append(normalize_album_track(t, album_id))
    return tracks


async def search_by_style(artist_id: str, genre: str = "", limit: int = 25) -> list[dict]:
    """
    Find stylistically similar tracks via Deezer's related-artists endpoint.
    Returns top tracks from each related artist — genuine algorithmic similarity.
    """
    return await get_related_artist_tracks(artist_id, tracks_per_artist=3, max_artists=8)


async def get_related_artist_tracks(
    artist_id: str,
    tracks_per_artist: int = 3,
    max_artists: int = 8,
) -> list[dict]:
    """
    Fetch top tracks from artists Deezer considers related to the given artist.
    These are the most genuine "sounds similar" recommendations available
    without Spotify-style audio feature data.
    """
    data = await _get(f"/artist/{artist_id}/related", {"limit": max_artists})
    related = data.get("data", [])
    if not related:
        return []

    # Fetch top tracks from each related artist in parallel
    async def top_tracks(a: dict) -> list[dict]:
        d = await _get(f"/artist/{a['id']}/top", {"limit": tracks_per_artist})
        return [normalize(t) for t in d.get("data", [])]

    results = await asyncio.gather(*[top_tracks(a) for a in related])
    out = []
    for batch in results:
        out.extend(batch)
    return out


# ─── Normalisation ────────────────────────────────────────────────────────────

def _artwork_from_track(raw: dict) -> str:
    """
    Derive album artwork URL from a Deezer track object.

    All Deezer track objects carry md5_image regardless of which endpoint
    they came from (search, artist/top, album/tracks, lookup). The album
    sub-object is absent for album/tracks responses, so we always prefer
    building the URL from md5_image rather than from album.cover_medium.
    """
    md5 = raw.get("md5_image") or (raw.get("album") or {}).get("md5_image", "")
    if md5:
        return f"https://cdn-images.dzcdn.net/images/cover/{md5}/250x250-000000-80-0-0.jpg"
    # Final fallback: album sub-object covers (present on search/top tracks)
    album = raw.get("album") or {}
    return album.get("cover_medium") or album.get("cover_big") or ""


def normalize(raw: dict) -> dict:
    """Convert a Deezer track (from search/top/lookup) to internal format."""
    artist = raw.get("artist") or {}
    album  = raw.get("album")  or {}

    return {
        "id":          str(raw.get("id", "")),
        "title":       raw.get("title") or raw.get("title_short", "Unknown"),
        "artist":      artist.get("name", "Unknown"),
        "artist_id":   str(artist.get("id", "")),
        "genre":       "hiphop",
        "raw_genre":   "Hip-Hop/Rap",
        "mood":        "chill",
        "energy":      0.5,
        "valence":     0.5,
        "acousticness": 0.3,
        "tempo_bpm":   120.0,
        "danceability": 0.5,
        "previewUrl":  raw.get("preview"),
        "artworkUrl":  _artwork_from_track(raw),
        "album":       album.get("title", ""),
        "album_id":    str(album.get("id", "0")),
        "releaseYear": str(raw.get("release_date", ""))[:4],
    }


def normalize_album_track(raw: dict, album_id: str) -> dict:
    """
    Album track objects from /album/{id}/tracks have no album sub-object
    but do carry md5_image, which _artwork_from_track() uses to build the URL.
    """
    result = normalize(raw)
    result["album_id"] = str(album_id)
    return result
