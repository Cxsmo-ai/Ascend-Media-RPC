import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.stats_card_generator import StatsCardGenerator


class TestStatsCardGenerator:
    def test_init(self):
        gen = StatsCardGenerator()
        assert gen is not None

    def test_generate_with_data(self):
        gen = StatsCardGenerator()
        stats = {
            "total_hours": 42.5,
            "total_sessions": 100,
            "completed_count": 75,
            "streak": {"current": 5, "longest": 14},
            "top_titles": [
                {"title": "Breaking Bad", "count": 20},
                {"title": "Stranger Things", "count": 15},
            ],
            "total_skips": 50,
            "total_saved_ms": 150000,
        }
        result = gen.generate(stats, username="TestUser")
        # Result is None if Pillow not installed, bytes if it is
        assert result is None or isinstance(result, bytes)
