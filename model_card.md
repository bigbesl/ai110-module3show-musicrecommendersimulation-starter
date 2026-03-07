# 🎧 Model Card: VibeFinder 1.0

## 1. Model Name

**VibeFinder 1.0**

---

## 2. Intended Use

This recommender suggests up to 5 songs from a small catalog based on a user's preferred genre, mood, energy level, and valence (positivity). It is designed for classroom exploration of how content-based filtering works — not for use as a real music product. It should not be used to make decisions about real users, artists, or playlists.

---

## 3. How the Model Works

When you give the system a taste profile — for example, "I like pop, I want happy songs, my target energy is 0.85" — it reads every song in the catalog and gives each one a score based on how well it matches your preferences.

- If the song's genre matches yours, it gets 2 bonus points (the biggest reward).
- If the song's mood matches yours, it gets 1 bonus point.
- The system calculates how close the song's energy is to your target on a 0–1 scale, then adds that as extra points. A perfect energy match adds 1.0; a complete mismatch adds 0.0.
- The same calculation is done for valence (how positive or bright the song sounds).

After scoring all songs, the system sorts them from highest to lowest and returns the top five with an explanation of why each was chosen.

---

## 4. Data

- **Catalog size:** 20 songs in `data/songs.csv`
- **Genres represented:** pop, lofi, rock, ambient, jazz, synthwave, indie pop, electronic, country, funk
- **Moods represented:** happy, chill, intense, relaxed, moody, focused, melancholy, energetic, sad
- **Added songs:** 10 new songs were added to the original 10 to improve genre and mood diversity
- **Limitations:** Country, funk, and electronic each have only 1–2 songs. Pop and lofi are overrepresented (4–5 songs each). The dataset reflects a narrow slice of musical taste and does not include hip-hop, R&B, classical, or non-English genres.

---

## 5. Strengths

- Works very well for users whose favorite genre is pop or lofi, since those genres have the most songs in the catalog.
- The explanation output (e.g., "genre match (+2.0) | mood match (+1.0)") makes it easy to understand exactly why each song was recommended — this is called **explainability**, and it's something many real AI systems lack.
- The scoring is simple enough that a human can verify or override it manually.
- For the "Chill Lofi" profile, the top 4 results all felt intuitively correct: low energy, chill or relaxed mood, high acousticness.

---

## 6. Limitations and Bias

- **Filter bubble by genre:** Because genre is worth twice as much as mood, users with a specific genre preference will almost always see the same genre recycled at the top, even if a song from a different genre would actually match their energy and mood better.
- **Small catalog amplifies bias:** With only 20 songs, a rock fan has only 3 options. The system has no way to be diverse or surprising.
- **No learning:** The system cannot observe whether users skip or replay songs. It will keep recommending the same top-5 forever, which would frustrate real users quickly.
- **Equal feature weights assume everyone is the same:** Some listeners care far more about tempo or danceability than mood. The fixed weights do not adapt to individual listening styles.
- **Underrepresented genres get penalized:** A user who prefers funk or country will only ever get 1 genre-match result, then fall back on energy/valence similarity, which may surface pop songs instead of what they actually want.

---

## 7. Evaluation

Three distinct user profiles were tested:

1. **High-Energy Pop Fan** (`genre: pop, mood: happy, energy: 0.85`) — Top results were "Sunrise City" and "Golden Hour." Both are pop/happy tracks with energy around 0.78–0.82. Results felt accurate and musically appropriate.

2. **Chill Lofi Listener** (`genre: lofi, mood: chill, energy: 0.38`) — "Library Rain" and "Midnight Coding" came out on top, both genuine lofi/chill tracks. Results felt correct.

3. **Intense Rock Head** (`genre: rock, mood: intense, energy: 0.92`) — The top 3 were all rock/intense songs ("Shatter," "Voltage Spike," "Storm Runner"). However, #4 was a pop song ("Gym Hero") because it matched the mood and energy even though it's not rock. This showed that mood weight can pull in unexpected genre crossovers.

**Experiment — halving genre weight:** When genre weight was changed from 2.0 to 1.0, energy and valence similarity became more influential. The pop fan started seeing synthwave and indie pop results. This suggested the genre weight is the single biggest driver of result "correctness" for genre-specific users.

---

## 8. Future Work

1. **Add a diversity penalty** so the same artist or genre can't appear more than twice in the top 5.
2. **Learn weights from user feedback** — if a user skips a song, lower that feature's weight; if they replay it, increase it.
3. **Expand the catalog** with at least 5 songs per genre so every user type gets a real range of recommendations.
4. **Add tempo-range matching** so a user who wants 90–100 BPM gets penalized for songs at 160 BPM even if the genre matches.
5. **Support collaborative filtering** — compare this user's profile against profiles of other users and recommend what similar listeners enjoyed.

---

## 9. Personal Reflection

Building this recommender made it clear that a recommendation system is not "intelligent" — it's just math applied to a table of numbers. What surprised me most was how much the **weight choices** shape the system's personality. A genre weight of 2.0 makes it feel like a genre radio station. Drop that to 0.5 and it starts feeling like a mood-based playlist generator. Real platforms like Spotify likely tune these weights using hundreds of millions of skip and replay signals, which is a form of machine learning this simulation completely skips.

The most important thing I learned is that bias in a recommender is not just about bad data — it's also baked into the design decisions about what to reward. Choosing to weight genre twice as heavily as mood is itself a bias toward genre-first listeners, and users who navigate music by feel or energy would be poorly served by this system as built.

Human judgment still matters in deciding which features to include, how to weight them, and when to override the algorithm in favor of fairness or variety.
