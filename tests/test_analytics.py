import os
import sys
import time
import pytest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


class TestAnalytics:
    def setup_method(self):
        self.tmpdir = tempfile.mkdtemp()
        from src.core.analytics import AnalyticsDB
        self.db = AnalyticsDB(
            db_path=os.path.join(self.tmpdir, "analytics.json"),
            sqlite_path=os.path.join(self.tmpdir, "analytics.db")
        )

    def test_start_and_end_session(self):
        sid = self.db.start_session("Test Movie", "2024", "tt1234", "movie", "", "Device", 7200000)
        assert sid > 0
        result = self.db.end_session(sid, 3600000)
        assert result is True

    def test_total_stats(self):
        self.db.start_session("Movie A", "", "tt1", "movie", "", "Dev", 5000)
        stats = self.db.get_total_stats()
        assert "total_sessions" in stats
        assert stats["total_sessions"] >= 1

    def test_add_skip(self):
        self.db.add_skip(30000)
        stats = self.db.get_advanced_stats()
        assert stats.get("total_skips", 0) >= 1

    def test_skip_provider_stats(self):
        self.db.add_skip_with_provider(5000, "introdb", "intro")
        self.db.add_skip_with_provider(3000, "videoskip", "mature")
        provider_stats = self.db.get_skip_provider_stats()
        assert isinstance(provider_stats, list)

    def test_skip_category_stats(self):
        self.db.add_skip_with_provider(5000, "introdb", "intro")
        cat_stats = self.db.get_skip_category_stats()
        assert isinstance(cat_stats, list)

    def test_daily_stats(self):
        daily = self.db.get_daily_stats(7)
        assert len(daily) == 7

    def test_search_history(self):
        self.db.start_session("Breaking Bad", "S1E1", "tt123", "tv", "", "Dev", 5000)
        results = self.db.search_history("Breaking")
        assert isinstance(results, list)

    def test_genre_breakdown(self):
        genres = self.db.get_genre_breakdown()
        assert isinstance(genres, list)

    def test_streak(self):
        streak = self.db.get_streak()
        assert "current" in streak
        assert "longest" in streak

    def test_filtered_history(self):
        self.db.start_session("Test", "", "", "movie", "", "Dev", 10000)
        result = self.db.get_filtered_history("all")
        assert isinstance(result, list)

    def test_grouped_by_show(self):
        self.db.start_session("Show A", "S1E1", "", "tv", "", "Dev", 5000)
        self.db.start_session("Show A", "S1E2", "", "tv", "", "Dev", 5000)
        result = self.db.get_grouped_by_show()
        assert isinstance(result, list)

    def test_weekly_report(self):
        report = self.db.get_weekly_report()
        assert isinstance(report, dict)

    def test_monthly_report(self):
        report = self.db.get_monthly_report()
        assert isinstance(report, dict)
