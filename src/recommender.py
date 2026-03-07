"""
Core recommendation logic for the Music Recommender Simulation.

Contains both a functional API (load_songs, score_song, recommend_songs)
used by main.py, and an OOP API (Song, UserProfile, Recommender)
used by the test suite.
"""

import csv
from typing import List, Dict, Tuple
from dataclasses import dataclass


# ---------------------------------------------------------------------------
# Data classes (required by tests/test_recommender.py)
# ---------------------------------------------------------------------------

@dataclass
class Song:
    """Represents a song and its audio attributes."""
    id: int
    title: str
    artist: str
    genre: str
    mood: str
    energy: float
    tempo_bpm: float
    valence: float
    danceability: float
    acousticness: float


@dataclass
class UserProfile:
    """Represents a user's taste preferences."""
    favorite_genre: str
    favorite_mood: str
    target_energy: float
    likes_acoustic: bool


# ---------------------------------------------------------------------------
# OOP Recommender (required by tests/test_recommender.py)
# ---------------------------------------------------------------------------

class Recommender:
    """Scores and ranks Song objects against a UserProfile."""

    def __init__(self, songs: List[Song]):
        self.songs = songs

    def _score(self, user: UserProfile, song: Song) -> Tuple[float, List[str]]:
        """Return (score, reasons) for one song given a user profile."""
        score = 0.0
        reasons = []

        if song.genre == user.favorite_genre:
            score += 2.0
            reasons.append("genre match (+2.0)")

        if song.mood == user.favorite_mood:
            score += 1.0
            reasons.append("mood match (+1.0)")

        energy_sim = round(1.0 - abs(song.energy - user.target_energy), 2)
        score += energy_sim
        reasons.append(f"energy similarity (+{energy_sim:.2f})")

        if user.likes_acoustic:
            acoustic_bonus = round(song.acousticness * 0.5, 2)
            score += acoustic_bonus
            reasons.append(f"acoustic bonus (+{acoustic_bonus:.2f})")

        return score, reasons

    def recommend(self, user: UserProfile, k: int = 5) -> List[Song]:
        """Return the top-k songs sorted by descending score."""
        scored = sorted(self.songs, key=lambda s: self._score(user, s)[0], reverse=True)
        return scored[:k]

    def explain_recommendation(self, user: UserProfile, song: Song) -> str:
        """Return a human-readable explanation of why song was recommended."""
        _, reasons = self._score(user, song)
        return ", ".join(reasons)


# ---------------------------------------------------------------------------
# Functional API (required by src/main.py)
# ---------------------------------------------------------------------------

def load_songs(csv_path: str) -> List[Dict]:
    """Load songs from a CSV file and return a list of dicts with typed values."""
    songs = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            songs.append({
                "id":           int(row["id"]),
                "title":        row["title"],
                "artist":       row["artist"],
                "genre":        row["genre"],
                "mood":         row["mood"],
                "energy":       float(row["energy"]),
                "tempo_bpm":    float(row["tempo_bpm"]),
                "valence":      float(row["valence"]),
                "danceability": float(row["danceability"]),
                "acousticness": float(row["acousticness"]),
            })
    print(f"Loaded {len(songs)} songs from {csv_path}")
    return songs


def score_song(user_prefs: Dict, song: Dict) -> Tuple[float, List[str]]:
    """
    Score a single song against user preferences.

    Scoring recipe:
      +2.0  genre match
      +1.0  mood match
      +0..1 energy similarity  (1 - |song_energy - target_energy|)
      +0..1 valence similarity (1 - |song_valence - target_valence|)  if provided
    Returns (score, reasons).
    """
    score = 0.0
    reasons = []

    if song["genre"] == user_prefs.get("genre"):
        score += 2.0
        reasons.append("genre match (+2.0)")

    if song["mood"] == user_prefs.get("mood"):
        score += 1.0
        reasons.append("mood match (+1.0)")

    energy_sim = round(1.0 - abs(song["energy"] - user_prefs.get("energy", 0.5)), 2)
    score += energy_sim
    reasons.append(f"energy similarity (+{energy_sim:.2f})")

    if "valence" in user_prefs:
        valence_sim = round(1.0 - abs(song["valence"] - user_prefs["valence"]), 2)
        score += valence_sim
        reasons.append(f"valence similarity (+{valence_sim:.2f})")

    return round(score, 2), reasons


def recommend_songs(user_prefs: Dict, songs: List[Dict], k: int = 5) -> List[Tuple[Dict, float, str]]:
    """
    Score every song, sort descending, and return the top-k results.

    Each result is a tuple of (song_dict, score, explanation_string).
    """
    scored = []
    for song in songs:
        score, reasons = score_song(user_prefs, song)
        explanation = " | ".join(reasons)
        scored.append((song, score, explanation))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:k]
