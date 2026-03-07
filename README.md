# 🎵 Music Recommender Simulation

## Project Summary

This project simulates how a basic music recommendation system works using content-based filtering. Given a user's taste profile — their preferred genre, mood, energy level, and valence — the system scores every song in the catalog and returns the top-k matches ranked by relevance. It mirrors the logic behind real platforms like Spotify's "Radio" feature, but intentionally simplified so the decision process is transparent and easy to inspect.

---

## How The System Works

Real-world recommenders like Spotify or YouTube use a combination of **collaborative filtering** (what similar users listened to) and **content-based filtering** (matching song attributes to your taste). This simulation focuses entirely on content-based filtering.

**Algorithm Recipe**

Each song is scored against the user profile using four rules:

| Rule | Points |
|---|---|
| Genre match | +2.0 |
| Mood match | +1.0 |
| Energy similarity `(1 - abs(song_energy - target_energy))` | 0.0 – 1.0 |
| Valence similarity `(1 - abs(song_valence - target_valence))` | 0.0 – 1.0 |

Songs are then sorted from highest to lowest score, and the top-k are returned with explanations.

**Key objects:**

- `Song` — stores id, title, artist, genre, mood, energy, tempo_bpm, valence, danceability, acousticness
- `UserProfile` — stores favorite_genre, favorite_mood, target_energy, likes_acoustic
- `Recommender` — OOP class that wraps a song list and exposes `recommend()` and `explain_recommendation()`
- `score_song` / `recommend_songs` — functional API used by the CLI runner

**Data flow:**

```
Input (User Prefs)
      ↓
Loop over every song in songs.csv
      ↓
score_song() → (numeric score, list of reasons)
      ↓
Sort all songs by score descending
      ↓
Return top-k (song, score, explanation)
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
   py src/main.py
   ```

### Running Tests

```bash
py -m pytest
```

---

## Experiments You Tried

**Profile variety test** — Running three profiles (High-Energy Pop, Chill Lofi, Intense Rock) confirmed the genre weight (+2.0) is the dominant factor. Every profile's top results matched genre first, then used mood and energy as tiebreakers.

**Genre-weight halved (2.0 → 1.0)** — When genre weight was reduced, energy and valence similarity became much more influential. A "pop/happy" user started seeing synthwave and indie pop songs in their top 3 because the energy profiles were very close. Results felt less "correct" to genre fans but more musically adventurous.

**Mood removed** — Removing the mood check had the smallest impact. Songs that matched genre and energy tended to also share mood, suggesting mood and genre are correlated in this small dataset.

---

## Limitations and Risks

- The catalog is only 20 songs, so genre-heavy scoring creates a "filter bubble" — a rock fan will see only 3 rock songs recycled every time.
- The system has no memory; it cannot learn from skips or replays.
- Genres like funk and country have only one song, so users with those preferences get poor results.
- Valence and danceability are scored equally even though different listeners weight them very differently.
- No diversity penalty — the same artist can appear multiple times in the top 5.

---

## Reflection

See [model_card.md](model_card.md) for a full analysis of strengths, biases, and future work.

Recommenders feel "smart" but are really just math on numbers. The surprising part of building this was realizing how much the **weight choices** — not the data — determine the personality of the system. Doubling the genre weight made it feel like a genre radio station; halving it made it feel more like a mood mixer. Real platforms likely tune these weights using millions of skip/replay signals, which is a form of learning this simulation completely lacks.
