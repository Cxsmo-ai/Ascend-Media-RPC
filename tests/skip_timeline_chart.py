"""Render a per-episode timeline of skip segments grouped by provider+category.

Pulls live data via SkipManager (per-provider probe), then renders:
  1. An ASCII Gantt-style timeline per episode (printed to stdout)
  2. A PNG chart per episode at data/skip_charts/<slug>.png

Usage:
    python tests/skip_timeline_chart.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.core.config import DEFAULT_CONFIG, load_config
from src.core.skip_manager import SkipManager

EPISODES = [
    {"name": "Stranger Things S2E3", "slug": "stranger_things_s2e3",
     "imdb_id": "tt4574334", "tmdb_id": 66732, "title": "Stranger Things",
     "season": 2, "episode": 3, "is_movie": False, "year": "2016"},
    {"name": "Breaking Bad S1E3", "slug": "breaking_bad_s1e3",
     "imdb_id": "tt0903747", "tmdb_id": 1396, "title": "Breaking Bad",
     "season": 1, "episode": 3, "is_movie": False, "year": "2008"},
    {"name": "Game of Thrones S2E3", "slug": "got_s2e3",
     "imdb_id": "tt0944947", "tmdb_id": 1399, "title": "Game of Thrones",
     "season": 2, "episode": 3, "is_movie": False, "year": "2011"},
]

# Color per category
CAT_COLORS = {
    "intro":           "#3b82f6",  # blue
    "outro":           "#8b5cf6",  # purple
    "credits":         "#a855f7",
    "recap":           "#10b981",  # green
    "preview":         "#14b8a6",
    "filler":          "#84cc16",
    "jumpscare_minor": "#f59e0b",  # amber
    "jumpscare_major": "#ef4444",  # red
    "scare":           "#dc2626",
    "mature":          "#ec4899",  # pink
}

def cat_color(t):
    t = (t or "").lower()
    for k, c in CAT_COLORS.items():
        if k in t:
            return c
    return "#6b7280"  # gray fallback


def make_manager():
    # Load the user's real config.json so SkipIt credentials are picked up
    try:
        config = load_config()
    except Exception:
        config = DEFAULT_CONFIG.copy()
    # Merge defaults for any missing keys without overriding loaded values
    for k, v in DEFAULT_CONFIG.items():
        config.setdefault(k, v)
    config["skip_mode"] = "auto"
    config["introdb_enabled"] = True
    config["aniskip_fallback"] = True
    config["tidb_enabled"] = True
    config["remote_json_enabled"] = bool(config.get("remote_json_url"))
    config["videoskip_enabled"] = True
    config["notscare_major_enabled"] = True
    config["notscare_minor_enabled"] = True
    config["skipme_enabled"] = True
    config["skipit_enabled"] = bool(config.get("skipit_token"))
    return SkipManager(config)


def probe_all(sm, ep):
    """Return {provider: [segments]}."""
    out = {}
    if sm.tidb_enabled:
        out["tidb"] = sm._fetch_tidb(ep["imdb_id"], ep["season"], ep["episode"], tmdb_id=ep["tmdb_id"]) or []
    if sm.introdb_enabled:
        out["introdb"] = sm._fetch_introdb(ep["tmdb_id"], ep["season"], ep["episode"], imdb_id=ep["imdb_id"]) or []
    if sm.videoskip_enabled:
        out["videoskip"] = sm._fetch_videoskip(ep["title"], ep["season"], ep["episode"]) or []
    if sm.notscare_major_enabled or sm.notscare_minor_enabled:
        out["notscare"] = sm._fetch_notscare(
            ep["title"], ep["season"], ep["episode"], ep["is_movie"], ep["imdb_id"], ep["year"]) or []
    if sm.skipme_enabled:
        try:
            out["skipme"] = sm._fetch_skipme(
                ep["imdb_id"], ep["season"], ep["episode"], ep["is_movie"], ep["tmdb_id"]) or []
        except Exception:
            out["skipme"] = []
    if sm.skipit_enabled and sm.skipit_auth.token:
        try:
            out["skipit"] = sm._fetch_skipit(
                ep["tmdb_id"], ep["season"], ep["episode"], ep["is_movie"]) or []
        except Exception as e:
            print(f"    skipit error: {e}")
            out["skipit"] = []
    if sm.aniskip_fallback:
        try:
            mid = sm._get_mal_id(ep["imdb_id"])
            out["aniskip"] = sm._fetch_aniskip(mid, ep["episode"]) if mid else []
            out["aniskip"] = out["aniskip"] or []
        except Exception:
            out["aniskip"] = []
    if sm.remote_json_enabled and sm.REMOTE_JSON_URL:
        try:
            out["remote_json"] = sm._fetch_remote_json(ep["imdb_id"], ep["season"], ep["episode"]) or []
        except Exception:
            out["remote_json"] = []
    return out


# ---------- ASCII renderer ----------
BAR_WIDTH = 60

def fmt_time(s):
    s = int(s)
    return f"{s//60:02d}:{s%60:02d}"

def render_ascii(ep_name, results, total_seconds):
    print()
    print("=" * 78)
    print(f"  {ep_name}   (timeline 0..{fmt_time(total_seconds)})")
    print("=" * 78)
    # Build a flat list (provider, segment)
    rows = []
    for prov, segs in results.items():
        for s in segs:
            rows.append((prov, s))
    if not rows:
        print("  (no segments)")
        return

    # sort by start
    rows.sort(key=lambda r: float(r[1].get("start", 0)))
    # Header axis
    axis = ["."] * BAR_WIDTH
    for i in range(0, BAR_WIDTH, BAR_WIDTH // 6):
        axis[i] = "|"
    print("  " + f"{'provider':<11} {'category':<18} {'start':>8} {'end':>8} {'dur':>7}  " + "".join(axis))
    print("  " + "-" * (11 + 1 + 18 + 1 + 8 + 1 + 8 + 1 + 7 + 2 + BAR_WIDTH))

    for prov, s in rows:
        try:
            st = float(s.get("start", 0))
            en = float(s.get("end", 0))
        except Exception:
            continue
        cat = s.get("type", "?")
        bar = [" "] * BAR_WIDTH
        i_start = max(0, int(st / total_seconds * BAR_WIDTH))
        i_end = min(BAR_WIDTH - 1, int(en / total_seconds * BAR_WIDTH))
        if i_end < i_start:
            i_end = i_start
        # pick a glyph by category
        glyph = "#"
        cl = cat.lower()
        if "intro" in cl: glyph = "I"
        elif "outro" in cl or "credits" in cl: glyph = "O"
        elif "recap" in cl: glyph = "R"
        elif "preview" in cl: glyph = "P"
        elif "filler" in cl: glyph = "F"
        elif "scare" in cl or "jump" in cl: glyph = "!"
        elif "mature" in cl or "sex" in cl or "violence" in cl: glyph = "M"
        for i in range(i_start, i_end + 1):
            bar[i] = glyph
        print(f"  {prov:<11} {cat:<18} {fmt_time(st):>8} {fmt_time(en):>8} {en-st:>6.1f}s  " + "".join(bar))

    # Legend
    print()
    print("  Legend:  I=intro  O=outro/credits  R=recap  P=preview  F=filler"
          "  !=scare  M=mature")


# ---------- PNG renderer ----------
def render_png(ep, results, total_seconds, out_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    providers = list(results.keys())
    fig_h = max(2.5, 0.55 * len(providers) + 1.5)
    fig, ax = plt.subplots(figsize=(13, fig_h))

    yticks = []
    ylabels = []
    legend_seen = {}

    for i, prov in enumerate(providers):
        segs = results[prov]
        y = i
        yticks.append(y)
        ylabels.append(f"{prov}\n({len(segs)} segs)")
        # subtle row background
        ax.axhspan(y - 0.45, y + 0.45,
                   color=("#f3f4f6" if i % 2 == 0 else "#ffffff"), zorder=0)
        for s in segs:
            try:
                st = float(s.get("start", 0))
                en = float(s.get("end", 0))
            except Exception:
                continue
            cat = s.get("type", "?")
            color = cat_color(cat)
            ax.barh(y, en - st, left=st, height=0.6,
                    color=color, edgecolor="#111827", linewidth=0.6, zorder=2)
            # label
            mid = (st + en) / 2.0
            ax.text(mid, y, cat, ha="center", va="center",
                    fontsize=8, color="white", zorder=3,
                    bbox=dict(facecolor=color, edgecolor="none", pad=1.2, alpha=0.0))
            ax.text(st, y + 0.32, f"{int(st)}s", fontsize=6.5, color="#374151", zorder=3)
            ax.text(en, y + 0.32, f"{int(en)}s", fontsize=6.5, color="#374151",
                    ha="right", zorder=3)
            legend_seen[cat.lower().split()[0] if cat else ""] = color

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    ax.invert_yaxis()
    ax.set_xlim(0, max(total_seconds, 1))
    ax.set_xlabel("Episode timeline (seconds)")
    ax.set_title(f"Skip Pipeline Segments  —  {ep['name']}")
    ax.grid(axis="x", linestyle=":", color="#9ca3af", alpha=0.6, zorder=1)

    # Legend by category color (deduped)
    handles = []
    seen = set()
    for cat in legend_seen:
        c = cat_color(cat)
        key = (cat, c)
        if key in seen: continue
        seen.add(key)
        handles.append(Patch(color=c, label=cat or "?"))
    if handles:
        ax.legend(handles=handles, loc="upper right", fontsize=8,
                  framealpha=0.95, ncol=min(4, len(handles)))

    plt.tight_layout()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fig.savefig(out_path, dpi=140)
    plt.close(fig)
    return out_path


def main():
    sm = make_manager()
    out_dir = os.path.join(os.path.dirname(__file__), "..", "data", "skip_charts")
    out_dir = os.path.abspath(out_dir)

    for ep in EPISODES:
        print(f"\n>>> Probing {ep['name']} ...")
        t0 = time.time()
        results = probe_all(sm, ep)
        dt = time.time() - t0
        print(f"    fetched in {dt:.1f}s")

        # Episode max time = max segment end + a small buffer, fall back to 3600s
        max_end = 0.0
        for segs in results.values():
            for s in segs:
                try: max_end = max(max_end, float(s.get("end", 0)))
                except Exception: pass
        total = max(int(max_end * 1.05), 1800)

        render_ascii(ep["name"], results, total)
        png = os.path.join(out_dir, f"{ep['slug']}.png")
        render_png(ep, results, total, png)
        print(f"    wrote chart -> {png}")


if __name__ == "__main__":
    main()
