# 🎵 WaveForm Web

## Project Summary

WaveForm Web is a music discovery app that lets you search any song and explore its "sonic universe" — a live, interactive graph of related tracks, artists, and albums built from real streaming data. When you hover over any node in the graph, a 30-second Deezer preview plays and the background transforms: a music video plays silently behind the graph, or the album's dominant color washes across the screen as a fallback. Genres are detected automatically using a multi-source pipeline (iTunes → MusicBrainz → Deezer) and displayed on hover. Recent searches are saved locally so you can jump back to previous sessions instantly.

---

## How The System Works

Most music apps treat recommendations as a black box. WaveForm makes the connections visible — every edge in the graph has a reason: same artist, same album, stylistically similar, or algorithmically recommended. You can filter by node type to isolate just the relationships that matter to you.

**Graph Construction**

When you search a song, the backend fetches data from Deezer's public API and builds a force-directed graph:

| Node type | What it represents |
|---|---|
| `your-song` | The track you searched |
| `same-artist` | Other songs by the same artist from Deezer |
| `same-album` | Other tracks from the same album |
| `similar-style` | Deezer's "related tracks" for that song |
| `top-pick` | Top-charting tracks by the same artist |

Edges connect nodes that share an artist, album, or recommendation relationship. The graph is laid out using D3's force simulation so clusters naturally emerge — an artist's catalog pulls together, similar-style tracks orbit nearby.

**Genre Detection Pipeline**

Genre labels are resolved in three tiers, falling through to the next if the previous returns nothing useful:

```
1. iTunes Search API  ← most accurate for mainstream + Asian artists
         ↓ (fallback)
2. MusicBrainz tags   ← crowdsourced, filtered to tags with ≥ 2 votes
         ↓ (fallback)
3. Deezer genre field ← broad category only
```

MusicBrainz queries use `artist:"name" AND recording:"title"` for disambiguation, so artists with common names (e.g. "MIKE", "Jay") resolve to the correct person.

**Background Visuals Pipeline**

On hover, the backend runs two tasks in parallel:

```
Hover event
     ├─ Canvas API extracts dominant color from album art (immediate)
     │        ↓
     │   Radial gradient fills background as fallback
     │
     └─ yt-dlp searches YouTube for official music video (async)
              ↓ (if found)
         YouTube embed plays muted in background, color gradient hides
```

YouTube results are cached to disk so repeat searches are instant. The Deezer 30-second audio preview plays over the video — the video is always muted.

**Key modules:**

- `src/api.py` — FastAPI app; serves the graph endpoint, YouTube lookup, and static files
- `src/graph_builder.py` — fetches Deezer data and assembles the D3-compatible node/link JSON
- `src/itunes_client.py` — iTunes + Deezer genre detection with persistent HTTP clients
- `src/musicbrainz_client.py` — MusicBrainz tag lookup with rate limiting and disambiguation
- `static/app.js` — D3 force graph, hover audio/video logic, legend filters, search history
- `static/index.html` / `static/style.css` — dark-themed single-page UI

**Data flow:**

```
User types a song
      ↓
GET /api/graph?song=...
      ↓
Deezer search → top track → related tracks + artist tracks + album tracks
      ↓
attach_genres() runs iTunes/MB/Deezer in parallel per node
      ↓
D3 force graph renders nodes + links
      ↓
Hover → Deezer preview plays + background video or color loads
```

---

## Getting Started

### Setup

1. Create a virtual environment (optional but recommended):

   ```bash
   python -m venv .venv
   source .venv/bin/activate      # Mac or Linux
   .venv\Scripts\activate         # Windows
   ```

2. Install dependencies:

   ```bash
   pip install -r requirements.txt
   ```

3. Run the app:

   ```bash
   py -m uvicorn src.api:app --port 8011
   ```

4. Open `http://localhost:8011` in your browser.

### Running Tests

```bash
py -m pytest
```

---

## Design Decisions Worth Noting

**iTunes-first genre detection** — Deezer's genre field is too broad ("Pop", "Rap/Hip Hop"). iTunes returns specific subgenres like "Alternative Rap" or "City Pop" and handles non-English artist names far better than MusicBrainz.

**yt-dlp over YouTube Data API** — The YouTube Data API costs 100 quota units per search with a 10,000/day cap, which burns through in a single debug session. yt-dlp fetches the same data with no API key and no quota. Videos are filtered to exclude lyric videos, audio-only uploads, covers, reactions, and live performances — only official music videos pass.

**Disk-persistent YouTube cache** — Video IDs are cached to `.yt_cache.json` so re-hovering the same song or restarting the server doesn't re-search YouTube.

**`_currentHoverId` race prevention** — Fetching a YouTube video takes 1–3 seconds. If the user moves to a different node before the fetch completes, the stale result is discarded instead of overwriting the new node's background.

---

## Limitations and Risks

- Deezer previews are capped at 30 seconds — there is no way to play full tracks without a Deezer OAuth token.
- yt-dlp search quality depends on YouTube's organic results; obscure tracks may surface the wrong video.
- MusicBrainz has limited coverage for non-English artists; iTunes is a better source but also has gaps.
- The graph shows up to ~15 nodes to keep the layout readable; very prolific artists get truncated.
- No user accounts or persistent preferences — the graph resets on every search.

---

## Reflection

See [model_card.md](model_card.md) for a full analysis of the original simulation's strengths, biases, and future work.

The jump from a scored CSV recommender to a live graph was mostly about embracing external APIs as a data source rather than a local dataset. The surprising design problem wasn't the graph layout or the audio — it was **genre detection**. A single song title like "Leadbelly" or an artist name like "MIKE" can match dozens of wrong entries across iTunes, Deezer, and MusicBrainz. The solution — anchoring every genre query to both artist name and song title, then requiring multi-vote consensus on MusicBrainz tags — is less elegant than a single API call but far more accurate. Real platforms solve this with canonical identifiers (Spotify track IDs, ISRCs); this app has to reconstruct that disambiguation from scratch on every search.
