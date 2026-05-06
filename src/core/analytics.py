import os
import json
import time
from datetime import datetime, timedelta
from .logger import logger

class AnalyticsDB:
    """Manages session-based analytics for Stremio RPC activity tracking."""
    def __init__(self, db_path="data/analytics.json"):
        self.db_path = db_path
        self.sessions = []
        self.total_skips = 0
        self.total_saved_ms = 0
        self.load()

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
        try:
            with open(self.db_path, "w") as f:
                json.dump({
                    "sessions": self.sessions[-500:], # Keep last 500 sessions
                    "total_skips": self.total_skips,
                    "total_saved_ms": self.total_saved_ms
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save analytics: {e}")

    def start_session(self, title, subtitle, imdb_id, media_type, image_url, device, total_duration_ms):
        # Use timestamp as a unique-enough ID for local storage
        session_id = int(time.time() * 1000)
        session = {
            "id": session_id,
            "title": title,
            "subtitle": subtitle,
            "imdb_id": imdb_id,
            "type": media_type,
            "image_url": image_url,
            "device": device,
            "duration": total_duration_ms,
            "start_time": int(time.time()),
            "end_time": None,
            "watch_time": 0
        }
        self.sessions.append(session)
        self.save()
        return session_id

    def end_session(self, session_id, final_position_ms):
        # Bug 17: Find by ID instead of index because list can truncate
        for session in reversed(self.sessions):
            if session.get("id") == session_id:
                session["end_time"] = int(time.time())
                session["watch_time"] = final_position_ms
                self.save()
                return True
        return False

    def add_skip(self, saved_ms):
        self.total_skips += 1
        self.total_saved_ms += saved_ms
        self.save()

    def get_total_stats(self):
        total_watch_ms = sum(s.get("watch_time", 0) for s in self.sessions)
        
        # Calculate Top Titles
        counts = {}
        completed = 0
        for s in self.sessions:
            title = s.get("title", "Unknown")
            counts[title] = counts.get(title, 0) + 1
            # Mark as completed if watched more than 90%
            dur = s.get("duration", 0)
            watched = s.get("watch_time", 0)
            if dur > 0 and (watched / dur) > 0.9:
                completed += 1
        
        sorted_titles = sorted([{"title": k, "count": v} for k, v in counts.items()], key=lambda x: x["count"], reverse=True)

        return {
            "total_hours": round(total_watch_ms / 3600000, 1),
            "total_sessions": len(self.sessions),
            "completed_count": completed,
            "top_titles": sorted_titles[:5]
        }

    def get_daily_stats(self, days=7):
        now = datetime.now()
        history = []
        
        for i in range(days - 1, -1, -1):
            target_date = (now - timedelta(days=i)).strftime("%Y-%m-%d")
            # Sum watch time for this day
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
