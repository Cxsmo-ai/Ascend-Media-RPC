import os
import json
import time
import sqlite3
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from .logger import logger

class AnalyticsDB:
    """Manages session-based analytics for Stremio RPC activity tracking.
    
    Supports both legacy JSON and SQLite backends. SQLite is used when
    sqlite_path is provided; otherwise falls back to JSON.
    """
    def __init__(self, db_path="data/analytics.json", sqlite_path: Optional[str] = None):
        self.db_path = db_path
        self.sqlite_path = sqlite_path or os.path.join("data", "analytics.db")
        self.sessions = []
        self.total_skips = 0
        self.total_saved_ms = 0
        self._lock = threading.Lock()
        self._use_sqlite = True
        self._init_sqlite()
        self._migrate_json_to_sqlite()

    def _init_sqlite(self):
        os.makedirs(os.path.dirname(self.sqlite_path), exist_ok=True)
        try:
            conn = sqlite3.connect(self.sqlite_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    title TEXT,
                    subtitle TEXT,
                    imdb_id TEXT,
                    type TEXT,
                    image_url TEXT,
                    device TEXT,
                    duration INTEGER DEFAULT 0,
                    start_time INTEGER,
                    end_time INTEGER,
                    watch_time INTEGER DEFAULT 0,
                    genre TEXT DEFAULT '',
                    rating REAL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS skip_stats (
                    id INTEGER PRIMARY KEY CHECK (id = 1),
                    total_skips INTEGER DEFAULT 0,
                    total_saved_ms INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO skip_stats (id, total_skips, total_saved_ms)
                VALUES (1, 0, 0)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_start_time
                ON sessions(start_time)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_title
                ON sessions(title)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_sessions_imdb_id
                ON sessions(imdb_id)
            """)
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"SQLite init failed, falling back to JSON: {e}")
            self._use_sqlite = False
            self.load()

    def _migrate_json_to_sqlite(self):
        if not self._use_sqlite:
            return
        if not os.path.exists(self.db_path):
            return
        try:
            with open(self.db_path, "r") as f:
                data = json.load(f)
            json_sessions = data.get("sessions", [])
            if not json_sessions:
                return
            conn = sqlite3.connect(self.sqlite_path)
            existing = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
            if existing > 0:
                conn.close()
                return
            for s in json_sessions:
                conn.execute(
                    "INSERT OR IGNORE INTO sessions "
                    "(id, title, subtitle, imdb_id, type, image_url, device, duration, start_time, end_time, watch_time) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (s.get("id"), s.get("title", ""), s.get("subtitle", ""),
                     s.get("imdb_id", ""), s.get("type", ""), s.get("image_url", ""),
                     s.get("device", ""), s.get("duration", 0), s.get("start_time", 0),
                     s.get("end_time"), s.get("watch_time", 0))
                )
            conn.execute(
                "UPDATE skip_stats SET total_skips = ?, total_saved_ms = ? WHERE id = 1",
                (data.get("total_skips", 0), data.get("total_saved_ms", 0))
            )
            conn.commit()
            conn.close()
            logger.info(f"Analytics: Migrated {len(json_sessions)} sessions from JSON to SQLite")
        except Exception as e:
            logger.error(f"Analytics migration error: {e}")

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.sqlite_path)
        conn.row_factory = sqlite3.Row
        return conn

    def load(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        if os.path.exists(self.db_path):
            try:
                with open(self.db_path, "r") as f:
                    data = json.load(f)
                    self.sessions = data.get("sessions", [])
                    self.total_skips = data.get("total_skips", 0)
                    self.total_saved_ms = data.get("total_saved_ms", 0)
            except Exception as e:
                logger.error(f"Failed to load analytics: {e}")

    def save(self):
        if self._use_sqlite:
            return
        try:
            with open(self.db_path, "w") as f:
                json.dump({
                    "sessions": self.sessions[-500:],
                    "total_skips": self.total_skips,
                    "total_saved_ms": self.total_saved_ms
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save analytics: {e}")

    def start_session(self, title, subtitle, imdb_id, media_type, image_url, device, total_duration_ms):
        session_id = int(time.time() * 1000)
        if self._use_sqlite:
            with self._lock:
                try:
                    conn = self._get_conn()
                    conn.execute(
                        "INSERT INTO sessions "
                        "(id, title, subtitle, imdb_id, type, image_url, device, duration, start_time) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (session_id, title, subtitle, imdb_id, media_type,
                         image_url, device, total_duration_ms, int(time.time()))
                    )
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"Analytics start_session error: {e}")
        else:
            session = {
                "id": session_id, "title": title, "subtitle": subtitle,
                "imdb_id": imdb_id, "type": media_type, "image_url": image_url,
                "device": device, "duration": total_duration_ms,
                "start_time": int(time.time()), "end_time": None, "watch_time": 0
            }
            self.sessions.append(session)
            self.save()
        return session_id

    def end_session(self, session_id, final_position_ms):
        if self._use_sqlite:
            with self._lock:
                try:
                    conn = self._get_conn()
                    conn.execute(
                        "UPDATE sessions SET end_time = ?, watch_time = ? WHERE id = ?",
                        (int(time.time()), final_position_ms, session_id)
                    )
                    conn.commit()
                    conn.close()
                    return True
                except Exception as e:
                    logger.error(f"Analytics end_session error: {e}")
                    return False
        else:
            for session in reversed(self.sessions):
                if session.get("id") == session_id:
                    session["end_time"] = int(time.time())
                    session["watch_time"] = final_position_ms
                    self.save()
                    return True
            return False

    def add_skip(self, saved_ms):
        if self._use_sqlite:
            with self._lock:
                try:
                    conn = self._get_conn()
                    conn.execute(
                        "UPDATE skip_stats SET total_skips = total_skips + 1, "
                        "total_saved_ms = total_saved_ms + ? WHERE id = 1",
                        (saved_ms,)
                    )
                    conn.commit()
                    conn.close()
                except Exception as e:
                    logger.error(f"Analytics add_skip error: {e}")
        else:
            self.total_skips += 1
            self.total_saved_ms += saved_ms
            self.save()

    def get_total_stats(self):
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                row = conn.execute(
                    "SELECT COALESCE(SUM(watch_time), 0) as total_ms, "
                    "COUNT(*) as total_sessions "
                    "FROM sessions"
                ).fetchone()
                total_watch_ms = row["total_ms"]
                total_sessions = row["total_sessions"]
                completed = conn.execute(
                    "SELECT COUNT(*) as cnt FROM sessions "
                    "WHERE duration > 0 AND CAST(watch_time AS REAL) / duration > 0.9"
                ).fetchone()["cnt"]
                top_titles = conn.execute(
                    "SELECT title, COUNT(*) as cnt FROM sessions "
                    "GROUP BY title ORDER BY cnt DESC LIMIT 5"
                ).fetchall()
                conn.close()
                return {
                    "total_hours": round(total_watch_ms / 3600000, 1),
                    "total_sessions": total_sessions,
                    "completed_count": completed,
                    "top_titles": [{"title": r["title"], "count": r["cnt"]} for r in top_titles]
                }
            except Exception as e:
                logger.error(f"Analytics get_total_stats error: {e}")
                return {"total_hours": 0, "total_sessions": 0, "completed_count": 0, "top_titles": []}

        total_watch_ms = sum(s.get("watch_time", 0) for s in self.sessions)
        counts: Dict[str, int] = {}
        completed = 0
        for s in self.sessions:
            title = s.get("title", "Unknown")
            counts[title] = counts.get(title, 0) + 1
            dur = s.get("duration", 0)
            watched = s.get("watch_time", 0)
            if dur > 0 and (watched / dur) > 0.9:
                completed += 1
        sorted_titles = sorted([{"title": k, "count": v} for k, v in counts.items()],
                               key=lambda x: x["count"], reverse=True)
        return {
            "total_hours": round(total_watch_ms / 3600000, 1),
            "total_sessions": len(self.sessions),
            "completed_count": completed,
            "top_titles": sorted_titles[:5]
        }

    def get_daily_stats(self, days=7):
        now = datetime.now()
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                history = []
                for i in range(days - 1, -1, -1):
                    target = now - timedelta(days=i)
                    day_start = int(target.replace(hour=0, minute=0, second=0).timestamp())
                    day_end = int(target.replace(hour=23, minute=59, second=59).timestamp())
                    row = conn.execute(
                        "SELECT COALESCE(SUM(watch_time), 0) as ms FROM sessions "
                        "WHERE start_time >= ? AND start_time <= ?",
                        (day_start, day_end)
                    ).fetchone()
                    history.append({
                        "date": target.strftime("%Y-%m-%d"),
                        "total_watch_minutes": round(row["ms"] / 60000, 1)
                    })
                conn.close()
                return history
            except Exception as e:
                logger.error(f"Analytics get_daily_stats error: {e}")
                return []

        history = []
        for i in range(days - 1, -1, -1):
            target_date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            daily_ms = 0
            for s in self.sessions:
                s_date = datetime.fromtimestamp(s.get("start_time", 0)).strftime("%Y-%m-%d")
                if s_date == target_date:
                    daily_ms += s.get("watch_time", 0)
            history.append({
                "date": target_date,
                "total_watch_minutes": round(daily_ms / 60000, 1)
            })
        return history

    def get_recent_sessions(self, limit=50):
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                rows = conn.execute(
                    "SELECT title, subtitle, image_url, start_time, watch_time "
                    "FROM sessions ORDER BY start_time DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                conn.close()
                return [{
                    "title": r["title"] or "Unknown",
                    "subtitle": r["subtitle"] or "",
                    "image_url": r["image_url"] or "",
                    "started_at": r["start_time"] or 0,
                    "duration_watched_ms": r["watch_time"] or 0
                } for r in rows]
            except Exception as e:
                logger.error(f"Analytics get_recent_sessions error: {e}")
                return []

        formatted = []
        for s in sorted(self.sessions, key=lambda x: x.get("start_time", 0), reverse=True)[:limit]:
            formatted.append({
                "title": s.get("title", "Unknown"),
                "subtitle": s.get("subtitle", ""),
                "image_url": s.get("image_url", ""),
                "started_at": s.get("start_time", 0),
                "duration_watched_ms": s.get("watch_time", 0)
            })
        return formatted

    def search_history(self, query: str, limit: int = 50) -> List[Dict]:
        """Search watch history by title."""
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                rows = conn.execute(
                    "SELECT title, subtitle, image_url, start_time, watch_time "
                    "FROM sessions WHERE title LIKE ? ORDER BY start_time DESC LIMIT ?",
                    (f"%{query}%", limit)
                ).fetchall()
                conn.close()
                return [{
                    "title": r["title"], "subtitle": r["subtitle"],
                    "image_url": r["image_url"], "started_at": r["start_time"],
                    "duration_watched_ms": r["watch_time"]
                } for r in rows]
            except Exception as e:
                logger.error(f"Analytics search error: {e}")
                return []
        return [s for s in self.get_recent_sessions(500)
                if query.lower() in (s.get("title", "")).lower()][:limit]

    def get_genre_breakdown(self) -> List[Dict]:
        """Get watch time broken down by genre."""
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                rows = conn.execute(
                    "SELECT genre, COUNT(*) as cnt, SUM(watch_time) as total_ms "
                    "FROM sessions WHERE genre != '' GROUP BY genre ORDER BY total_ms DESC"
                ).fetchall()
                conn.close()
                return [{"genre": r["genre"], "count": r["cnt"],
                         "hours": round(r["total_ms"] / 3600000, 1)} for r in rows]
            except Exception as e:
                logger.error(f"Analytics genre breakdown error: {e}")
        return []

    def get_peak_hours(self) -> List[Dict]:
        """Get most active viewing hours."""
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                rows = conn.execute(
                    "SELECT CAST(strftime('%H', start_time, 'unixepoch', 'localtime') AS INTEGER) as hour, "
                    "COUNT(*) as cnt FROM sessions GROUP BY hour ORDER BY hour"
                ).fetchall()
                conn.close()
                return [{"hour": r["hour"], "sessions": r["cnt"]} for r in rows]
            except Exception as e:
                logger.error(f"Analytics peak hours error: {e}")
        return []

    def get_streak(self) -> Dict:
        """Calculate current and longest watch streaks."""
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                rows = conn.execute(
                    "SELECT DISTINCT date(start_time, 'unixepoch', 'localtime') as d "
                    "FROM sessions ORDER BY d"
                ).fetchall()
                conn.close()
                dates = [datetime.strptime(r["d"], "%Y-%m-%d") for r in rows]
                if not dates:
                    return {"current": 0, "longest": 0}
                current = 1
                longest = 1
                streak = 1
                for i in range(1, len(dates)):
                    if (dates[i] - dates[i-1]).days == 1:
                        streak += 1
                    else:
                        streak = 1
                    longest = max(longest, streak)
                today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
                if dates[-1] >= today - timedelta(days=1):
                    current = streak
                else:
                    current = 0
                return {"current": current, "longest": longest}
            except Exception as e:
                logger.error(f"Analytics streak error: {e}")
        return {"current": 0, "longest": 0}

    def get_advanced_stats(self) -> Dict:
        """Combined advanced statistics."""
        base = self.get_total_stats()
        base["genre_breakdown"] = self.get_genre_breakdown()
        base["peak_hours"] = self.get_peak_hours()
        base["streak"] = self.get_streak()
        if self._use_sqlite:
            try:
                conn = self._get_conn()
                row = conn.execute(
                    "SELECT total_skips, total_saved_ms FROM skip_stats WHERE id = 1"
                ).fetchone()
                base["total_skips"] = row["total_skips"] if row else 0
                base["total_saved_ms"] = row["total_saved_ms"] if row else 0
                avg = conn.execute(
                    "SELECT AVG(watch_time) as avg_ms FROM sessions WHERE watch_time > 0"
                ).fetchone()
                base["avg_session_minutes"] = round((avg["avg_ms"] or 0) / 60000, 1)
                conn.close()
            except Exception as e:
                logger.error(f"Analytics advanced stats error: {e}")
        return base
