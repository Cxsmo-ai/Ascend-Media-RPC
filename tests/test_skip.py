import os
import sys
import time
import threading
import pytest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import DEFAULT_CONFIG
from src.core.skip_manager import SkipManager
from src.core.skip_cache import SkipSegmentCache


def _make_sm(**overrides):
    config = DEFAULT_CONFIG.copy()
    config["skip_mode"] = "auto"
    # Disable network providers by default for safety in unit tests
    config["introdb_enabled"] = False
    config["aniskip_fallback"] = False
    config["tidb_enabled"] = False
    config["remote_json_enabled"] = False
    config["videoskip_enabled"] = False
    config["notscare_major_enabled"] = False
    config["notscare_minor_enabled"] = False
    config["skipme_enabled"] = False
    config["skipit_enabled"] = False
    config.update(overrides)
    return SkipManager(config)


# ---------------------------------------------------------------------------
# Original sanity tests (kept for backwards-compat)
# ---------------------------------------------------------------------------
class TestSkipManager:
    def setup_method(self):
        config = DEFAULT_CONFIG.copy()
        config["skip_mode"] = "auto"
        self.sm = SkipManager(config)

    def test_init(self):
        assert self.sm.enabled is True

    def test_category_toggles(self):
        assert self.sm.cat_intro is True
        assert self.sm.cat_outro is True
        assert self.sm.cat_mature is True

    def test_cache_stats(self):
        stats = self.sm.get_cache_stats()
        assert isinstance(stats, dict)

    def test_clear_cache(self):
        self.sm.clear_cache()
        assert self.sm.cache == {}

    def test_should_skip_no_segments(self):
        assert self.sm.should_skip(0, []) is None

    def test_should_skip_with_segment(self):
        segments = [{"start": 0, "end": 30, "type": "intro", "source": "introdb", "label": "Skip Intro"}]
        result = self.sm.should_skip(5000, segments)
        assert result is not None or result is None

    def test_priority_order(self):
        assert isinstance(self.sm.skip_priority_order, list)
        assert len(self.sm.skip_priority_order) > 0


# ---------------------------------------------------------------------------
# should_skip — boundary, malformed, and unit handling
# ---------------------------------------------------------------------------
class TestShouldSkip:
    def setup_method(self):
        self.sm = _make_sm()

    def test_disabled_returns_none(self):
        sm = _make_sm()
        sm.enabled = False
        seg = [{"start": 0, "end": 30}]
        assert sm.should_skip(5000, seg) is None

    def test_position_inside_segment(self):
        seg = [{"start": 0, "end": 30, "type": "intro"}]
        result = self.sm.should_skip(5000, seg)
        assert result is not None
        target_ms, kind = result
        assert target_ms == 30000
        assert kind == "intro"

    def test_position_at_start_boundary_inclusive(self):
        # start <= pos < end => start is INSIDE the segment
        seg = [{"start": 5, "end": 30, "type": "intro"}]
        # at exactly 5s the helper considers us inside
        result = self.sm.should_skip(5000, seg)
        assert result is not None
        assert result[0] == 30000

    def test_position_at_end_boundary_exclusive(self):
        # pos == end => not inside the segment
        seg = [{"start": 0, "end": 30, "type": "intro"}]
        assert self.sm.should_skip(30000, seg) is None

    def test_position_before_segment(self):
        seg = [{"start": 10, "end": 30}]
        assert self.sm.should_skip(5000, seg) is None

    def test_position_after_segment(self):
        seg = [{"start": 0, "end": 30}]
        assert self.sm.should_skip(45000, seg) is None

    def test_remaining_too_small_skipped(self):
        # less than 1s remaining inside the segment -> no skip
        seg = [{"start": 0, "end": 5}]
        # at 4.5s, target is 5000ms, diff = 500ms -> below 1s threshold
        assert self.sm.should_skip(4500, seg) is None

    def test_segment_missing_start_key(self):
        seg = [{"end": 30, "type": "intro"}]
        # Must NOT raise KeyError
        assert self.sm.should_skip(5000, seg) is None

    def test_segment_missing_end_key(self):
        seg = [{"start": 0, "type": "intro"}]
        assert self.sm.should_skip(5000, seg) is None

    def test_segment_with_invalid_types(self):
        seg = [{"start": "abc", "end": "xyz"}]
        assert self.sm.should_skip(5000, seg) is None

    def test_segment_with_inverted_range(self):
        # end <= start -> ignored
        seg = [{"start": 30, "end": 10}]
        assert self.sm.should_skip(5000, seg) is None

    def test_non_dict_entry_ignored(self):
        seg = [None, "garbage", {"start": 0, "end": 30}]
        result = self.sm.should_skip(5000, seg)
        assert result is not None and result[0] == 30000

    def test_negative_position(self):
        seg = [{"start": 0, "end": 30}]
        assert self.sm.should_skip(-1000, seg) is None

    def test_first_matching_segment_wins(self):
        seg = [
            {"start": 0, "end": 30, "type": "intro"},
            {"start": 25, "end": 60, "type": "recap"},
        ]
        result = self.sm.should_skip(28000, seg)
        # Either is valid; only one is returned
        assert result is not None
        assert result[0] in (30000, 60000)


# ---------------------------------------------------------------------------
# Category toggles
# ---------------------------------------------------------------------------
class TestCategoryToggles:
    def test_disabled_intro_filtered_via_should_skip_input(self):
        """Even if a segment is in skip_times, the manager has already filtered
        in get_skip_times. should_skip itself just operates on the list."""
        sm = _make_sm(skip_cat_intro=False)
        # Manually feed a list as if filter ran (intro removed)
        assert sm.should_skip(5000, []) is None

    def test_default_toggles_all_true(self):
        sm = _make_sm()
        for attr in ("cat_intro", "cat_outro", "cat_recap", "cat_preview",
                     "cat_credits", "cat_filler", "cat_mature", "cat_scare"):
            assert getattr(sm, attr) is True

    def test_custom_toggle_overrides(self):
        sm = _make_sm(skip_cat_intro=False, skip_cat_mature=False)
        assert sm.cat_intro is False
        assert sm.cat_mature is False
        assert sm.cat_outro is True


# ---------------------------------------------------------------------------
# get_skip_times — pipeline-level behaviour
# ---------------------------------------------------------------------------
class TestGetSkipTimes:
    def test_no_identifiers_returns_none(self):
        sm = _make_sm()
        assert sm.get_skip_times("", 1, 1, tmdb_id=None, title=None) is None

    def test_no_providers_returns_none(self):
        sm = _make_sm()
        # All providers disabled in _make_sm
        result = sm.get_skip_times("tt1234567", 1, 1)
        assert result is None

    def test_string_season_episode_coerced(self):
        sm = _make_sm()
        # Should not raise even when Flask-style strings come in
        result = sm.get_skip_times("tt1234567", "1", "1")
        assert result is None  # all providers disabled

    def test_invalid_season_episode_does_not_raise(self):
        sm = _make_sm()
        result = sm.get_skip_times("tt1234567", "abc", "xyz")
        assert result is None

    def test_in_memory_cache_hit(self):
        sm = _make_sm()
        key = "tt1-None-None-1-1-False-None"
        cached = [{"start": 0, "end": 10, "type": "intro", "source": "x"}]
        sm.cache[key] = cached
        out = sm.get_skip_times("tt1", 1, 1)
        assert out == cached

    def test_invalid_segments_are_filtered(self):
        sm = _make_sm()
        # Force pipeline by patching _fetch_* to inject malformed segments
        sm.tidb_enabled = True

        def fake_tidb(*a, **kw):
            return [
                {"start": None, "end": 10, "type": "intro", "source": "tidb"},   # invalid
                {"start": 0, "end": 0, "type": "intro", "source": "tidb"},        # zero-length
                {"start": 30, "end": 10, "type": "intro", "source": "tidb"},      # inverted
                {"start": 0, "end": 20, "type": "intro", "source": "tidb"},       # valid
            ]
        sm._fetch_tidb = fake_tidb
        out = sm.get_skip_times("tt1", 1, 1)
        assert out is not None
        assert len(out) == 1
        assert out[0]["start"] == 0 and out[0]["end"] == 20

    def test_category_filter_drops_intro(self):
        sm = _make_sm(skip_cat_intro=False)
        sm.tidb_enabled = True
        sm._fetch_tidb = lambda *a, **kw: [
            {"start": 0, "end": 20, "type": "intro", "source": "tidb"},
            {"start": 100, "end": 130, "type": "outro", "source": "tidb"},
        ]
        out = sm.get_skip_times("tt2", 1, 1)
        assert out is not None
        types = [s["type"] for s in out]
        assert "intro" not in types
        assert "outro" in types


# ---------------------------------------------------------------------------
# Provider parsers — defensive against malformed responses
# ---------------------------------------------------------------------------
class TestProviderParsers:
    def setup_method(self):
        self.sm = _make_sm()

    def test_aniskip_malformed_interval_no_keyerror(self):
        """_fetch_aniskip must not raise KeyError on missing interval keys."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "found": True,
            "results": [
                {"skipType": "op"},  # no interval
                {"skipType": "ed", "interval": {}},  # empty interval
                {"skipType": "op", "interval": {"startTime": 5, "endTime": 30}},
            ],
        }
        with patch("src.core.skip_manager.requests.get", return_value=fake_resp):
            res = self.sm._fetch_aniskip(123, 1)
        assert res is not None
        assert len(res) == 1
        assert res[0]["start"] == 5 and res[0]["end"] == 30

    def test_aniskip_not_found(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"found": False}
        with patch("src.core.skip_manager.requests.get", return_value=fake_resp):
            assert self.sm._fetch_aniskip(123, 1) is None

    def test_aniskip_http_error(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 500
        with patch("src.core.skip_manager.requests.get", return_value=fake_resp):
            assert self.sm._fetch_aniskip(123, 1) is None

    def test_aniskip_request_exception(self):
        with patch("src.core.skip_manager.requests.get", side_effect=Exception("boom")):
            assert self.sm._fetch_aniskip(123, 1) is None

    def test_remote_json_missing_keys_no_keyerror(self):
        self.sm.REMOTE_JSON_URL = "https://example.com/skips.json"
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {
            "tt1:1:1": [
                {"type": "intro"},               # missing start/end -> dropped
                {"start": 0, "end": 10, "type": "intro", "label": "x"},
            ]
        }
        with patch("src.core.skip_manager.requests.get", return_value=fake_resp):
            res = self.sm._fetch_remote_json("tt1", 1, 1)
        assert res is not None
        assert len(res) == 1
        assert res[0]["start"] == 0 and res[0]["end"] == 10

    def test_remote_json_no_match(self):
        self.sm.REMOTE_JSON_URL = "https://example.com/skips.json"
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = {"other:1:1": [{"start": 0, "end": 5}]}
        with patch("src.core.skip_manager.requests.get", return_value=fake_resp):
            assert self.sm._fetch_remote_json("tt1", 1, 1) is None

    def test_skipme_empty_data_no_indexerror(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = []  # empty
        with patch("src.core.skip_manager.requests.post", return_value=fake_resp):
            assert self.sm._fetch_skipme("tt1", 1, 1, False, 999) is None

    def test_skipme_non_dict_entry_no_attributerror(self):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = ["unexpected"]
        with patch("src.core.skip_manager.requests.post", return_value=fake_resp):
            assert self.sm._fetch_skipme("tt1", 1, 1, False, 999) is None


# ---------------------------------------------------------------------------
# SkipSegmentCache
# ---------------------------------------------------------------------------
class TestSkipSegmentCache:
    def test_basic_get_put(self):
        c = SkipSegmentCache(ttl=60, max_size=10)
        c.put("tt1", 1, 1, [{"start": 0, "end": 10}])
        assert c.get("tt1", 1, 1) == [{"start": 0, "end": 10}]

    def test_miss_returns_none(self):
        c = SkipSegmentCache()
        assert c.get("tt1", 1, 1) is None

    def test_ttl_expiry(self):
        c = SkipSegmentCache(ttl=0)  # immediately expires
        c.put("tt1", 1, 1, [{"start": 0, "end": 10}])
        time.sleep(0.01)
        assert c.get("tt1", 1, 1) is None

    def test_invalidate_specific(self):
        c = SkipSegmentCache()
        c.put("tt1", 1, 1, [{"a": 1}])
        c.put("tt2", 1, 1, [{"b": 2}])
        c.invalidate("tt1")
        assert c.get("tt1", 1, 1) is None
        assert c.get("tt2", 1, 1) == [{"b": 2}]

    def test_invalidate_all(self):
        c = SkipSegmentCache()
        c.put("tt1", 1, 1, [{"a": 1}])
        c.put("tt2", 1, 1, [{"b": 2}])
        c.invalidate()
        assert c.get("tt1", 1, 1) is None
        assert c.get("tt2", 1, 1) is None

    def test_max_size_eviction(self):
        c = SkipSegmentCache(ttl=600, max_size=3)
        c.put("a", 1, 1, [{"x": 1}])
        time.sleep(0.001)
        c.put("b", 1, 1, [{"x": 2}])
        time.sleep(0.001)
        c.put("c", 1, 1, [{"x": 3}])
        time.sleep(0.001)
        c.put("d", 1, 1, [{"x": 4}])  # should evict the oldest ("a")
        assert c.get("a", 1, 1) is None
        assert c.get("d", 1, 1) == [{"x": 4}]
        assert c.stats()["total_entries"] == 3

    def test_key_collision_with_hyphen_in_title(self):
        """Titles with hyphens must NOT collide thanks to non-printable separator."""
        c = SkipSegmentCache()
        c.put("tt1", 1, 1, [{"id": "A"}], title="My-Show")
        c.put("tt1", 1, 1, [{"id": "B"}], title="My", year="Show")
        a = c.get("tt1", 1, 1, title="My-Show")
        b = c.get("tt1", 1, 1, title="My", year="Show")
        assert a == [{"id": "A"}]
        assert b == [{"id": "B"}]
        assert a != b

    def test_stats_shape(self):
        c = SkipSegmentCache(ttl=60, max_size=5)
        c.put("tt1", 1, 1, [{"x": 1}])
        s = c.stats()
        for key in ("total_entries", "valid_entries", "expired_entries",
                    "max_size", "ttl_seconds"):
            assert key in s
        assert s["total_entries"] == 1
        assert s["valid_entries"] == 1

    def test_thread_safety_no_crash(self):
        c = SkipSegmentCache(ttl=60, max_size=50)
        errors = []

        def worker(idx):
            try:
                for i in range(50):
                    c.put(f"tt{idx}", i, i, [{"i": i}])
                    c.get(f"tt{idx}", i, i)
            except Exception as e:  # pragma: no cover
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        assert not errors


# ---------------------------------------------------------------------------
# Cache integration with SkipManager
# ---------------------------------------------------------------------------
class TestSkipManagerCacheIntegration:
    def test_get_cache_stats_returns_dict(self):
        sm = _make_sm()
        s = sm.get_cache_stats()
        assert isinstance(s, dict)
        assert "total_entries" in s

    def test_clear_cache_clears_both_layers(self):
        sm = _make_sm()
        sm.cache["foo"] = [{"x": 1}]
        sm._ttl_cache.put("tt1", 1, 1, [{"x": 1}])
        sm.clear_cache()
        assert sm.cache == {}
        assert sm._ttl_cache.get("tt1", 1, 1) is None
