"""
MusicBrainz genre tag client for WaveForm Web.

Used as the second-tier genre source ONLY when iTunes returns a generic
Western genre (Pop, Rock, Hip-Hop/Rap, etc.). For Asian and other
specifically-categorised music, iTunes is already accurate (K-Pop, J-Pop,
Mandopop, Cantopop/HK-Pop) and MusicBrainz is not consulted.

Rate limit: MusicBrainz allows ~1 req/sec per IP. We use a semaphore
capped at 2 concurrent requests with a 0.5s sleep — ~2 req/sec.
"""

import asyncio
import httpx

_MB_BASE   = "https://musicbrainz.org/ws/2"
_HEADERS   = {"User-Agent": "WaveFormWeb/1.0 (music-recommender-app)"}
_cache: dict[str, str] = {}
_semaphore = asyncio.Semaphore(2)
_mb_client: httpx.AsyncClient | None = None


def _get_mb_client() -> httpx.AsyncClient:
    global _mb_client
    if _mb_client is None or _mb_client.is_closed:
        _mb_client = httpx.AsyncClient(headers=_HEADERS, timeout=8.0)
    return _mb_client

# iTunes genres that are too generic to display — MusicBrainz is consulted instead
ITUNES_GENERIC = {
    "Pop", "Rock", "Dance", "Alternative", "Electronic",
    "Hip-Hop/Rap", "Hip-Hop", "R&B/Soul", "R&B", "Soul",
    "Country", "Folk", "Metal", "Classical", "Jazz",
    "Soundtrack", "Music", "Singer/Songwriter",
}

# Tags that describe nationality, occupation, or non-genre attributes
_SKIP_TAGS = {
    "english", "french", "korean", "chinese", "japanese", "american",
    "british", "german", "spanish", "portuguese", "swedish", "italian",
    "norwegian", "canadian", "australian", "dutch", "belgian", "danish",
    "taiwanese", "hongkongese", "thai", "indonesian", "vietnamese",
    "male vocalist", "female vocalist", "male vocals", "female vocals",
    "singer", "vocalist", "boy group", "girl group", "group", "duo",
    "trio", "band", "actor", "actress", "comedian", "tv personality",
    "presenter", "model", "dancer", "producer", "dj",
    "seen live", "favorites", "favourite", "all", "unknown",
    "singer-songwriter",
}
# Decade / era tags
_SKIP_TAGS.update({f"{d}s" for d in range(1940, 2030, 10)})

# Very generic base genres — prefer a specific subgenre when available
_GENERIC_BASE = {
    "pop", "rock", "hip hop", "rap", "electronic", "dance",
    "r&b", "soul", "jazz", "classical", "country", "metal",
    "folk", "alternative", "indie", "funk", "blues",
}


async def get_artist_genre(artist_name: str, title_hint: str = "") -> str:
    """
    Return the most specific genre tag for an artist from MusicBrainz.
    If title_hint is provided, searches with recording context to disambiguate
    common names (e.g. "Mike" could be many artists — title pins the right one).
    Returns empty string if MB has no usable data.
    Results are cached by lowercased artist name.
    """
    key = artist_name.lower().strip()
    if key in _cache:
        return _cache[key]

    # Build query: if we have a title hint, add recording context to disambiguate
    if title_hint:
        query = f'artist:"{artist_name}" AND recording:"{title_hint}"'
    else:
        query = artist_name

    async with _semaphore:
        try:
            client = _get_mb_client()
            resp = await client.get(
                f"{_MB_BASE}/artist/",
                params={
                    "query": query,
                    "limit": 5,
                    "fmt":   "json",
                    "inc":   "tags",
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            _cache[key] = ""
            return ""
        finally:
            await asyncio.sleep(0.35)

    artists = data.get("artists", [])
    best = next((a for a in artists if int(a.get("score", 0)) >= 80), None)
    if not best:
        _cache[key] = ""
        return ""

    raw_tags = sorted(best.get("tags", []), key=lambda t: -t.get("count", 0))
    usable = [
        t for t in raw_tags
        if t.get("count", 0) >= 2          # require at least 2 votes to filter out joke/venue tags
        and len(t["name"].strip()) > 2
        and t["name"].lower().strip() not in _SKIP_TAGS
    ]

    if not usable:
        _cache[key] = ""
        return ""

    top_name = usable[0]["name"].lower().strip()

    # Prefer a specific subgenre over a generic base label
    if top_name in _GENERIC_BASE:
        for t in usable[1:]:
            if t.get("count", 0) >= 2 and t["name"].lower().strip() not in _GENERIC_BASE:
                genre = _title_tag(t["name"])
                _cache[key] = genre
                return genre

    genre = _title_tag(usable[0]["name"])
    _cache[key] = genre
    return genre


def _title_tag(tag: str) -> str:
    """Title-case a genre tag, preserving known acronyms."""
    overrides = {
        "r&b": "R&B", "rnb": "R&B",
        "j-pop": "J-Pop", "k-pop": "K-Pop", "c-pop": "C-Pop",
        "j-rock": "J-Rock", "k-rock": "K-Rock",
        "lo-fi": "Lo-Fi", "lo-fi hip hop": "Lo-Fi Hip Hop",
        "edm": "EDM", "uk garage": "UK Garage", "uk drill": "UK Drill",
        "afrobeats": "Afrobeats", "mandopop": "Mandopop",
        "cantopop": "Cantopop",
    }
    lower = tag.lower().strip()
    return overrides.get(lower, lower.title())
