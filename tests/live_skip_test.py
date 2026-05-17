"""Live end-to-end test of the skip pipeline against real providers.

Runs SkipManager.get_skip_times() against three real episodes and prints a
detailed report of which providers responded, any errors, and the merged
segments. Also exercises should_skip() against the merged result.

Usage:
    python tests/live_skip_test.py
"""
import os
import sys
import time
import json
import traceback

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import DEFAULT_CONFIG
from src.core.skip_manager import SkipManager


EPISODES = [
    {
        "name": "Stranger Things S2E3",
        "imdb_id": "tt4574334",
        "tmdb_id": 66732,
        "title": "Stranger Things",
        "season": 2,
        "episode": 3,
        "is_movie": False,
        "year": "2016",
    },
    {
        "name": "Breaking Bad S1E3",
        "imdb_id": "tt0903747",
        "tmdb_id": 1396,
        "title": "Breaking Bad",
        "season": 1,
        "episode": 3,
        "is_movie": False,
        "year": "2008",
    },
    {
        "name": "Game of Thrones S2E3",
        "imdb_id": "tt0944947",
        "tmdb_id": 1399,
        "title": "Game of Thrones",
        "season": 2,
        "episode": 3,
        "is_movie": False,
        "year": "2011",
    },
]


def fmt_seg(s):
    return (
        f"  [{s.get('source','?'):>12}] "
        f"{s.get('type','?'):>8} "
        f"{float(s.get('start',0)):>8.2f}s -> {float(s.get('end',0)):>8.2f}s "
        f"({float(s.get('end',0)) - float(s.get('start',0)):>6.2f}s)  "
        f"{s.get('label','')}"
    )


def make_manager():
    """Build a SkipManager with all providers turned on."""
    config = DEFAULT_CONFIG.copy()
    config["skip_mode"] = "auto"
    # Enable everything that doesn't need user-supplied auth
    config["introdb_enabled"] = True
    config["aniskip_fallback"] = True
    config["tidb_enabled"] = True
    # Remote JSON only runs if a URL is configured
    config["remote_json_enabled"] = bool(config.get("remote_json_url"))
    config["videoskip_enabled"] = True
    config["notscare_major_enabled"] = True
    config["notscare_minor_enabled"] = True
    config["skipme_enabled"] = True
    # SkipIt requires an auth token; only enable if present in env/config
    config["skipit_enabled"] = bool(config.get("skipit_token"))
    return SkipManager(config)


def per_provider_probe(sm, ep):
    """Call each enabled provider directly so we get a per-provider report
    instead of just the merged output."""
    probes = []
    if sm.tidb_enabled:
        probes.append(("tidb", lambda: sm._fetch_tidb(
            ep["imdb_id"], ep["season"], ep["episode"], tmdb_id=ep["tmdb_id"])))
    if sm.introdb_enabled:
        probes.append(("introdb", lambda: sm._fetch_introdb(
            ep["tmdb_id"], ep["season"], ep["episode"], imdb_id=ep["imdb_id"])))
    if sm.videoskip_enabled:
        probes.append(("videoskip", lambda: sm._fetch_videoskip(
            ep["title"], ep["season"], ep["episode"])))
    if sm.notscare_major_enabled or sm.notscare_minor_enabled:
        probes.append(("notscare", lambda: sm._fetch_notscare(
            ep["title"], ep["season"], ep["episode"], ep["is_movie"],
            ep["imdb_id"], ep["year"])))
    if sm.skipme_enabled:
        probes.append(("skipme", lambda: sm._fetch_skipme(
            ep["imdb_id"], ep["season"], ep["episode"], ep["is_movie"], ep["tmdb_id"])))
    if sm.remote_json_enabled and sm.REMOTE_JSON_URL:
        probes.append(("remote_json", lambda: sm._fetch_remote_json(
            ep["imdb_id"], ep["season"], ep["episode"])))
    if sm.aniskip_fallback:
        probes.append(("aniskip", lambda: _try_aniskip(sm, ep)))

    results = {}
    for name, fn in probes:
        t0 = time.time()
        try:
            res = fn()
            results[name] = {
                "ok": True,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "count": len(res) if res else 0,
                "segments": res or [],
                "error": None,
            }
        except Exception as e:
            results[name] = {
                "ok": False,
                "elapsed_ms": int((time.time() - t0) * 1000),
                "count": 0,
                "segments": [],
                "error": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc(),
            }
    return results


def _try_aniskip(sm, ep):
    mal_id = sm._get_mal_id(ep["imdb_id"])
    if not mal_id:
        return None
    return sm._fetch_aniskip(mal_id, ep["episode"])


def run():
    print("=" * 78)
    print("LIVE SKIP PIPELINE TEST")
    print("=" * 78)
    sm = make_manager()
    print(f"Providers enabled: tidb={sm.tidb_enabled} introdb={sm.introdb_enabled} "
          f"videoskip={sm.videoskip_enabled} notscare={sm.notscare_major_enabled} "
          f"skipme={sm.skipme_enabled} aniskip={sm.aniskip_fallback} "
          f"remote_json={sm.remote_json_enabled} skipit={sm.skipit_enabled}")
    print()

    overall = []

    for ep in EPISODES:
        print("-" * 78)
        print(f"EPISODE: {ep['name']}  (imdb={ep['imdb_id']}, tmdb={ep['tmdb_id']})")
        print("-" * 78)

        # 1) Per-provider probe
        probes = per_provider_probe(sm, ep)
        any_ok = False
        for name, info in probes.items():
            status = "OK " if info["ok"] else "ERR"
            print(f"  {status} {name:>12}  {info['elapsed_ms']:>5}ms  "
                  f"segments={info['count']}"
                  + (f"  error={info['error']}" if info["error"] else ""))
            if info["ok"] and info["count"] > 0:
                any_ok = True
                for s in info["segments"][:5]:
                    print(fmt_seg(s))

        # 2) Full pipeline (merged + filtered)
        sm.cache.clear()
        sm._ttl_cache.invalidate()
        t0 = time.time()
        try:
            merged = sm.get_skip_times(
                ep["imdb_id"], ep["season"], ep["episode"],
                tmdb_id=ep["tmdb_id"], title=ep["title"],
                is_movie=ep["is_movie"], year=ep["year"],
            )
            elapsed = int((time.time() - t0) * 1000)
            print()
            print(f"  PIPELINE merged result ({elapsed}ms): "
                  f"{len(merged) if merged else 0} segments")
            if merged:
                for s in merged:
                    print(fmt_seg(s))
            else:
                print("  (none)")

            # 3) Exercise should_skip()
            if merged:
                # pick the middle of the first segment
                first = merged[0]
                pos_ms = int((float(first["start"]) + 1.0) * 1000)
                hit = sm.should_skip(pos_ms, merged)
                print(f"  should_skip(@{pos_ms}ms) -> {hit}")
                # outside any segment
                miss = sm.should_skip(0, merged) if float(first["start"]) > 1 else None
                print(f"  should_skip(@0ms outside) -> {miss}")

            overall.append({
                "episode": ep["name"],
                "any_provider_ok": any_ok,
                "merged_count": len(merged) if merged else 0,
                "pipeline_ms": elapsed,
                "pipeline_error": None,
            })
        except Exception as e:
            print(f"  PIPELINE FAILED: {type(e).__name__}: {e}")
            traceback.print_exc()
            overall.append({
                "episode": ep["name"],
                "any_provider_ok": any_ok,
                "merged_count": 0,
                "pipeline_ms": int((time.time() - t0) * 1000),
                "pipeline_error": f"{type(e).__name__}: {e}",
            })
        print()

    print("=" * 78)
    print("SUMMARY")
    print("=" * 78)
    for o in overall:
        flag = "OK" if o["pipeline_error"] is None else "FAIL"
        print(f"  [{flag}] {o['episode']:<28}  "
              f"providers_responded={o['any_provider_ok']}  "
              f"merged_segments={o['merged_count']}  "
              f"pipeline_time={o['pipeline_ms']}ms"
              + (f"  err={o['pipeline_error']}" if o["pipeline_error"] else ""))

    # Exit non-zero only if pipeline actually crashed (not just no segments found)
    failed = [o for o in overall if o["pipeline_error"]]
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run())
