"""
Graph builder for WaveForm Web.

Converts iTunes API results into a D3-compatible node/link JSON structure.
Uses the existing score_song() function from recommender.py to rank songs
and identify top picks.

Node types:
  seed         – the song the user searched for
  artist_match – other songs by the same artist
  album_match  – other tracks from the same album (most sonically similar)
  style_match  – songs from stylistically adjacent artists
  top_pick     – top 5 scored songs (overrides the above types)
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from recommender import score_song

TOP_PICK_COUNT = 5


def build_graph(
    seed: dict,
    artist_songs: list[dict],
    album_songs: list[dict],
    style_songs: list[dict],
) -> dict:
    """
    Build a D3-compatible graph from a seed song and three pools of related songs.
    Returns {"nodes": [...], "links": [...]}.
    """
    seed_id = seed["id"]
    seen_ids: set[str] = {seed_id}
    nodes: list[dict] = []
    links: list[dict] = []

    user_prefs = {
        "genre": seed["genre"],
        "mood":  seed.get("mood", "chill"),
        "energy":  seed.get("energy", 0.5),
        "valence": seed.get("valence", 0.5),
    }

    candidates: list[tuple[dict, float, str]] = []

    # ── Artist matches ────────────────────────────────────────────────────────
    for song in artist_songs:
        if song["id"] in seen_ids:
            continue
        score, _ = score_song(user_prefs, song)
        candidates.append((song, score, "artist_match"))
        seen_ids.add(song["id"])

    # ── Album matches (exclude songs already captured via artist pool) ────────
    for song in album_songs:
        if song["id"] in seen_ids:
            continue
        score, _ = score_song(user_prefs, song)
        # Boost album matches slightly — same album is the strongest similarity signal
        candidates.append((song, score + 0.5, "album_match"))
        seen_ids.add(song["id"])

    # ── Style matches (exclude songs already captured above) ─────────────────
    seed_artist_id = seed.get("artist_id", "")
    for song in style_songs:
        if song["id"] in seen_ids:
            continue
        # Exclude songs by the exact same artist (already in artist pool)
        if song.get("artist_id") == seed_artist_id and seed_artist_id:
            continue
        if song["artist"].lower() == seed["artist"].lower():
            continue
        score, _ = score_song(user_prefs, song)
        candidates.append((song, score, "style_match"))
        seen_ids.add(song["id"])

    # Sort all candidates by score descending; top 5 become "top_pick"
    candidates.sort(key=lambda x: x[1], reverse=True)
    top_pick_ids = {c[0]["id"] for c in candidates[:TOP_PICK_COUNT]}

    # Seed node
    nodes.append(_make_node(seed, "seed", score=None))

    # Candidate nodes + links
    for song, score, link_type in candidates:
        node_type = "top_pick" if song["id"] in top_pick_ids else link_type
        nodes.append(_make_node(song, node_type, score=round(score, 2)))
        links.append(_make_link(seed_id, song["id"], link_type))

    return {"nodes": nodes, "links": links}


def _make_node(song: dict, node_type: str, score) -> dict:
    return {
        "id":          song["id"],
        "label":       song["title"],
        "artist":      song["artist"],
        "genre":       song.get("raw_genre", song["genre"]),
        "album":       song.get("album", ""),
        "releaseYear": song.get("releaseYear", ""),
        "score":       score,
        "previewUrl":  song.get("previewUrl"),
        "artworkUrl":  song.get("artworkUrl", ""),
        "nodeType":    node_type,
    }


def _make_link(source_id: str, target_id: str, link_type: str) -> dict:
    return {
        "source":   source_id,
        "target":   target_id,
        "linkType": link_type,
    }
