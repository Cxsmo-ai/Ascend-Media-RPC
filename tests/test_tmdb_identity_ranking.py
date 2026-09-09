from src.core.tmdb import TMDBClient


def test_exact_title_beats_similar_popular_title():
    items = [
        {"name": "The Mentalist: Special", "first_air_date": "2008-01-01"},
        {"name": "The Mentalist", "first_air_date": "2008-09-23"},
    ]
    ranked = sorted(items, key=lambda item: TMDBClient._search_result_rank(item, "The Mentalist", "2008"))
    assert ranked[0]["name"] == "The Mentalist"


def test_matching_year_beats_remake_for_same_title():
    items = [
        {"title": "Example", "release_date": "2025-01-01"},
        {"title": "Example", "release_date": "1999-01-01"},
    ]
    ranked = sorted(items, key=lambda item: TMDBClient._search_result_rank(item, "Example", "1999"))
    assert ranked[0]["release_date"].startswith("1999")
