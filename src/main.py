"""
Command line runner for the Music Recommender Simulation.

Runs the recommender against three distinct user profiles so you can
compare how the scoring behaves for different listener types.
"""

from recommender import load_songs, recommend_songs


def print_recommendations(profile_name: str, user_prefs: dict, songs: list, k: int = 5) -> None:
    """Print the top-k recommendations for a given user profile."""
    print(f"\n{'='*55}")
    print(f"  Profile: {profile_name}")
    print(f"  Prefs:   {user_prefs}")
    print(f"{'='*55}")

    recommendations = recommend_songs(user_prefs, songs, k=k)

    if not recommendations:
        print("  No recommendations found.")
        return

    for i, (song, score, explanation) in enumerate(recommendations, start=1):
        print(f"\n  #{i}  {song['title']} by {song['artist']}")
        print(f"       Genre: {song['genre']} | Mood: {song['mood']} | Energy: {song['energy']}")
        print(f"       Score: {score:.2f}")
        print(f"       Why:   {explanation}")


def main() -> None:
    songs = load_songs("data/songs.csv")

    profiles = [
        (
            "High-Energy Pop Fan",
            {"genre": "pop", "mood": "happy", "energy": 0.85, "valence": 0.85},
        ),
        (
            "Chill Lofi Listener",
            {"genre": "lofi", "mood": "chill", "energy": 0.38, "valence": 0.58},
        ),
        (
            "Intense Rock Head",
            {"genre": "rock", "mood": "intense", "energy": 0.92, "valence": 0.40},
        ),
    ]

    for name, prefs in profiles:
        print_recommendations(name, prefs, songs, k=5)

    print(f"\n{'='*55}\n")


if __name__ == "__main__":
    main()
