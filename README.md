# 🎵 WaveForm Web

## Base Project

This project extends the **AI110 Music Recommender Simulation** — a content-based filtering system that scored songs against a user profile using genre, mood, energy, and valence weights and returned ranked top-k matches from a local CSV catalog. That system was a CLI-only tool with no external data, no audio, and no visualization. WaveForm Web replaces the static CSV lookup with live streaming APIs, adds an interactive visual graph, and integrates real audio previews and music video playback.

---

## Project Summary

WaveForm Web is a music discovery app that lets you search any song and explore its "sonic universe" — a live, interactive graph of related tracks, artists, and albums built from real streaming data. When you hover over any node in the graph, a 30-second Deezer preview plays and the background transforms: a music video plays silently behind the graph, or the album's dominant color washes across the screen as a fallback. Genres are detected automatically using a multi-source AI pipeline (iTunes → MusicBrainz → Deezer) and displayed on hover. Recent searches are saved locally so you can jump back to previous sessions instantly.

---

## Architecture

```mermaid
flowchart TD
    User([Browser]) -->|types song name| FE[Frontend\napp.js · D3.js]

    FE -->|GET /api/graph?song=| API[FastAPI\nsrc/api.py]
    API -->|search + related tracks| Deezer[(Deezer\nPublic API)]
    Deezer -->|tracks + album art + preview URLs| API

    API -->|attach_genres per node| GP[Genre Pipeline]
    GP -->|artist + title query| iTunes[(iTunes\nSearch API)]
    GP -->|artist AND recording query| MB[(MusicBrainz\nAPI)]
    GP -->|fallback genre field| Deezer

    API -->|nodes + links JSON| FE
    FE -->|renders| Graph[D3 Force Graph]

    Graph -->|hover event| Hover[Hover Handler]
    Hover -->|Deezer previewUrl| Audio[Audio Preview\n30s clip]
    Hover -->|GET /api/youtube?artist=&title=| API
    API -->|yt-dlp search| YT[(YouTube\nyt-dlp)]
    YT -->|video ID| API
    API -->|videoId or null| Hover
    Hover -->|videoId found| BgVideo[Muted Video\nBackground]
    Hover -->|null: Canvas API| BgColor[Album Color\nGradient]

    FE -->|read/write| LS[(localStorage\nsearch history)]
```

**Major components:**
- `src/api.py` — FastAPI app; `/api/graph`, `/api/youtube`, `/api/suggest` endpoints
- `src/graph_builder.py` — builds D3-compatible node/link JSON from Deezer data
- `src/itunes_client.py` — iTunes + Deezer genre detection, persistent HTTP client
- `src/musicbrainz_client.py` — MusicBrainz tag lookup, rate limiting, artist disambiguation
- `static/app.js` — D3 force simulation, hover audio/video logic, legend filters, search history

---

## How The System Works

**Graph Construction**

When you search a song, the backend fetches data from Deezer's public API and builds a force-directed graph:

| Node type | What it represents |
|---|---|
| `your-song` | The track you searched |
| `same-artist` | Other songs by the same artist |
| `same-album` | Other tracks from the same album |
| `similar-style` | Deezer's "related tracks" for that song |
| `top-pick` | Top-charting tracks by the same artist |

Edges connect nodes that share an artist, album, or recommendation relationship. Clusters naturally emerge — an artist's catalog pulls together, similar-style tracks orbit nearby.

**Genre Detection Pipeline (AI Feature)**

The core AI feature is a multi-source genre detection pipeline that uses three external knowledge bases in sequence:

```
1. iTunes Search API  ← most accurate for mainstream + Asian artists
         ↓ (fallback)
2. MusicBrainz tags   ← crowdsourced, filtered to tags with ≥ 2 votes
         ↓ (fallback)
3. Deezer genre field ← broad category only
```

This is an AI-powered feature because it uses semantic disambiguation — the same query `MIKE` returns dozens of artists, but querying `artist:"MIKE" AND recording:"Leadbelly"` on MusicBrainz narrows to the correct underground rapper. The pipeline produces specific subgenre labels ("Alternative Rap", "City Pop", "Hypnagogic Pop") rather than coarse buckets, which meaningfully changes the tooltip data shown on every node hover.

**Background Visuals Pipeline**

On hover, the frontend runs two tasks in parallel:

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

**Data flow:**

```
User types a song
      ↓
GET /api/graph?song=...
      ↓
Deezer search → top track → related + artist + album tracks (parallel)
      ↓
attach_genres() resolves iTunes/MB/Deezer in parallel per node
      ↓
D3 force graph renders nodes + links in browser
      ↓
Hover → Deezer preview plays + yt-dlp fetches video ID in background
      ↓
Video found → muted YouTube iframe fills background
No video   → Canvas extracts album color → radial gradient fills background
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

## Demo Video

[Demo Video](https://youtu.be/jDa1IM6-y5w) 

---

## Demo Walkthrough

The following inputs demonstrate full end-to-end system behavior:

### Input 1 — Mainstream pop

**Search:** `Uptown Funk`

**Expected output:**
- Seed node: *Uptown Funk — Mark Ronson ft. Bruno Mars*, Genre: `Pop`
- ~5 same-artist nodes (other Bruno Mars songs), ~4 same-album nodes, ~4 similar-style nodes
- Hover seed node → official music video plays in background, Deezer 30s preview starts
- Graph layout: Bruno Mars cluster on one side, similar-style pop tracks orbiting outward

### Input 2 — Underground hip-hop

**Search:** `Leadbelly MIKE`

**Expected output:**
- Seed node: *Leadbelly — MIKE*, Genre: `Alternative Rap`
- Related nodes from MIKE's catalog and underground hip-hop adjacents
- Hover → album color gradient (no major-label MV available for many nodes)
- Genre correctly disambiguated to MIKE the rapper, not a blues artist

### Input 3 — Indie / alternative

**Search:** `Motion Sickness Phoebe Bridgers`

**Expected output:**
- Seed node: *Motion Sickness — Phoebe Bridgers*, Genre: `Indie Folk` or `Indie Pop`
- Same-album tracks from *Stranger in the Alps*
- Similar-style nodes: other indie-folk artists surfaced via Deezer's related-tracks API
- Hover → music video or warm amber/brown album color gradient

**Sample API response** for `GET /api/graph?song=Uptown+Funk` (abbreviated):

```json
{
  "nodes": [
    {
      "id": "116090910",
      "label": "Uptown Funk",
      "artist": "Mark Ronson",
      "genre": "Pop",
      "nodeType": "seed",
      "artworkUrl": "https://cdns-images.dzcdn.net/images/cover/...",
      "previewUrl": "https://cdns-images.dzcdn.net/stream/..."
    },
    {
      "id": "67238732",
      "label": "Just The Way You Are",
      "artist": "Bruno Mars",
      "genre": "Pop",
      "nodeType": "same-artist",
      ...
    }
  ],
  "links": [
    { "source": "116090910", "target": "67238732", "linkType": "same-artist" }
  ]
}
```

---

## Reliability Mechanisms

The system includes several reliability mechanisms that prevent failures from degrading the user experience:

**1. Multi-tier genre fallback**
If iTunes returns no match (e.g. very obscure artist), the system falls through to MusicBrainz, then to Deezer's coarse genre field. No node ever displays a blank genre — there is always a label, even if less specific.

**2. Disk-persistent YouTube cache (`.yt_cache.json`)**
Every resolved video ID is written to disk immediately after lookup. On server restart, past results are loaded back into memory. This prevents redundant searches and ensures the system degrades gracefully under high load — cached results return in under 1ms.

**3. `_currentHoverId` race guard**
YouTube video fetches take 1–5 seconds. If the user moves to a different node before the fetch resolves, the result is silently discarded via a token comparison (`_currentHoverId !== myId`). Without this, rapid hovering would cause stale video IDs to flash in the background of the wrong node.

**4. Color gradient fallback**
The Canvas API begins extracting the album's dominant color the instant a hover starts — before the YouTube fetch even begins. If no video is found (or the fetch errors), the color gradient is already visible. The background is never empty.

**5. MusicBrainz vote threshold**
MusicBrainz tags require ≥ 2 community votes to be used. This filters out joke tags, venue names, and one-off entries (e.g. "Relic Inn" appeared as a single-vote tag for Bruno Mars before this threshold was applied).

**6. Rate limiting on MusicBrainz**
A `Semaphore(2)` + 350ms delay between requests prevents MusicBrainz from rate-limiting the server when building a large graph. Without this, genre detection for 15 nodes in parallel would trigger HTTP 429 responses.

---

## AI Use in Development

This project was built collaboratively with Claude (Anthropic). Claude contributed to architecture decisions, debugging, and code generation throughout development.

**Helpful AI suggestions:**

- **`_currentHoverId` pattern**: When rapid hovering caused stale async video fetches to overwrite the wrong node's background, Claude suggested a token-comparison guard — each hover sets a unique ID, and any async callback checks whether that ID is still current before writing to the DOM. This was a non-obvious solution to a real race condition that would have required significant debugging without AI assistance.

- **`asyncio.gather` for parallel genre detection**: Claude suggested running iTunes, MusicBrainz, and Deezer lookups concurrently per node using `asyncio.gather`, cutting graph build time from ~8 seconds to ~2 seconds for a 15-node graph. The approach also suggested batching all nodes together so the three APIs are queried in parallel across nodes, not sequentially.

- **MusicBrainz Lucene query format**: Claude suggested the `artist:"name" AND recording:"title"` Lucene syntax for MusicBrainz, which correctly disambiguates artists with common names. A plain name search for "MIKE" returned blues musicians and session players before this fix.

**Flawed AI suggestions:**

- **YouTube Data API v3**: Claude initially recommended using the YouTube Data API v3 (official, well-documented). This was integrated and worked during testing, but the 10,000-unit daily quota was exhausted in a single debug session (each search costs 100 units). The entire feature broke and had to be rebuilt using yt-dlp, which has no quota. The original recommendation failed to account for development-time usage burning through production quota.

- **VEVO fallback query**: Claude suggested adding a third yt-dlp search query (`"{artist} {title} vevo"`) and increasing the result count from 5 to 8, reasoning that VEVO-hosted videos would rank higher with explicit mention. In practice, this changed the ranking of results in a way that caused previously-working video selections to return the wrong video for several songs. The change had to be reverted.

---

## Stretch Goals

### RAG Enhancement — Multi-Source Retrieval

The genre detection pipeline is a multi-source retrieval system. Rather than relying on a single knowledge base, the system queries three external sources in sequence and synthesizes the best available answer:

- **iTunes Search API** — queried first with `artist + title` anchoring to avoid ambiguous matches
- **MusicBrainz** — queried using Lucene syntax (`artist:"name" AND recording:"title"`) to retrieve community-tagged genre labels, filtered to entries with ≥ 2 votes
- **Deezer genre field** — used as a last-resort fallback when the above return nothing

This mirrors the RAG pattern: instead of retrieving from a vector database, the system retrieves from live knowledge APIs and returns the most specific, highest-confidence answer. The retrieval is not static — it runs on every graph load, so new tags added to MusicBrainz are reflected immediately.

**Where it lives:** `src/itunes_client.py` → `attach_genres()`, `src/musicbrainz_client.py` → `get_artist_genre()`

---

### Agentic Workflow — Multi-Step Reasoning Chain

The graph build and hover pipeline is an agentic workflow with branching decision steps:

```
Step 1  Search Deezer for seed track by name
           ↓
Step 2  Spawn 3 parallel retrieval tasks:
        artist_match pool | album_match pool | style_match pool
           ↓
Step 3  For each node, run genre detection chain:
        try iTunes → if empty, try MusicBrainz → if empty, use Deezer
           ↓
Step 4  User hovers a node → decision point:
        fetch YouTube video ID (async)
           ↓
Step 5  If video found → display muted iframe
        If not found   → extract album color via Canvas API → display gradient
```

Each step uses the output of the previous step to decide what to do next. The genre chain in Step 3 is a planning loop — it stops as soon as a satisfactory result is found rather than always querying all three sources. Step 5 is a tool-use decision: the system calls an external tool (yt-dlp) and chooses between two rendering paths based on the result.

**Where it lives:** `src/graph_builder.py`, `src/api.py` → `youtube_video()`, `static/app.js` → `triggerBackground()`

---

### Specialization Behavior — Constrained Output Filtering

The system applies two layers of specialized output constraints:

**`_is_real_mv()` classifier** — a constrained filter applied to every YouTube search result before accepting it. It rejects results whose titles contain keywords associated with non-official content: lyric videos, audio-only uploads, covers, karaoke, reactions, slowed/reverbed edits, nightcore, and live performances. Only results where the artist or title appears in the video title AND no disqualifying keyword is present are accepted.

```python
_NOT_MV = {"lyrics", "lyric", "audio", "visualizer", "cover", "karaoke",
           "reaction", "slowed", "reverb", "nightcore", "live at", "live in",
           "concert", "tour", "interview", "behind the scenes", "making of"}
```

**MusicBrainz vote threshold** — genre tags with fewer than 2 community votes are discarded. This constrains the system to only use genre labels that have been validated by multiple independent contributors, filtering out joke entries, one-off tags, and venue names.

Both constraints specialize system behavior: without them the outputs would be inconsistent and often wrong. With them, the system reliably returns official music videos and specific, accurate genre labels.

**Where it lives:** `src/api.py` → `_is_real_mv()`, `src/musicbrainz_client.py` → `get_artist_genre()`

---

### Test Harness

The project includes a pytest-based test suite in `tests/test_recommender.py` that evaluates the original recommendation engine on predefined inputs and verifies expected behavior:

| Test | Input | Expected output | Pass condition |
|---|---|---|---|
| `test_recommend_returns_songs_sorted_by_score` | Profile: genre=pop, mood=happy, energy=0.8 | Top result is the pop/happy song | `results[0].genre == "pop"` |
| `test_explain_recommendation_returns_non_empty_string` | Same profile + pop song | Non-empty explanation string | `isinstance(explanation, str) and explanation.strip() != ""` |

Run the full suite:

```bash
py -m pytest tests/ -v
```

Expected output:
```
tests/test_recommender.py::test_recommend_returns_songs_sorted_by_score PASSED
tests/test_recommender.py::test_explain_recommendation_returns_non_empty_string PASSED
2 passed in 0.12s
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
- The YouTube cache is ephemeral on serverless deployments (Vercel) — video lookups repeat on every cold start.

---

## Reflection

See [model_card.md](model_card.md) for a full analysis of the original simulation's strengths, biases, and future work.

The jump from a scored CSV recommender to a live graph was mostly about embracing external APIs as a data source rather than a local dataset. The surprising design problem wasn't the graph layout or the audio — it was **genre detection**. A single song title like "Leadbelly" or an artist name like "MIKE" can match dozens of wrong entries across iTunes, Deezer, and MusicBrainz. The solution — anchoring every genre query to both artist name and song title, then requiring multi-vote consensus on MusicBrainz tags — is less elegant than a single API call but far more accurate. Real platforms solve this with canonical identifiers (Spotify track IDs, ISRCs); this app has to reconstruct that disambiguation from scratch on every search.

The most instructive failure was the YouTube quota incident. Building with an officially-supported API felt like the right call, but the API's rate limits were designed for production traffic patterns, not iterative development. Switching to yt-dlp — a library that scrapes the same data without a key — was faster and more reliable for this use case. The tradeoff is fragility: YouTube can change its page structure at any time and break yt-dlp. For a production system, the right answer is probably a cached proxy layer in front of the official API, not a scraper.
