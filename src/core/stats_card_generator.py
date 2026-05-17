import io
import logging
import time
from typing import Dict, Optional

logger = logging.getLogger("stremio-rpc")

try:
    from PIL import Image, ImageDraw, ImageFont
    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False


class StatsCardGenerator:
    """Generates shareable PNG stats cards (Spotify Wrapped style)."""

    CARD_WIDTH = 1080
    CARD_HEIGHT = 1920
    BG_COLOR_TOP = (26, 26, 46)
    BG_COLOR_BOT = (15, 52, 96)
    ACCENT = (138, 43, 226)
    TEXT_WHITE = (255, 255, 255)
    TEXT_GRAY = (180, 180, 200)
    TEXT_GOLD = (255, 215, 0)

    def __init__(self):
        if not _PIL_AVAILABLE:
            logger.warning("Pillow not installed — stats card generation disabled")

    @staticmethod
    def _gradient_bg(width: int, height: int, top: tuple, bot: tuple) -> "Image.Image":
        img = Image.new("RGB", (width, height))
        pixels = img.load()
        for y in range(height):
            ratio = y / height
            r = int(top[0] + (bot[0] - top[0]) * ratio)
            g = int(top[1] + (bot[1] - top[1]) * ratio)
            b = int(top[2] + (bot[2] - top[2]) * ratio)
            for x in range(width):
                pixels[x, y] = (r, g, b)
        return img

    def _get_font(self, size: int) -> "ImageFont.FreeTypeFont":
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except Exception:
            try:
                return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", size)
            except Exception:
                return ImageFont.load_default()

    def generate(self, stats: Dict, username: str = "Viewer") -> Optional[bytes]:
        if not _PIL_AVAILABLE:
            return None

        img = self._gradient_bg(self.CARD_WIDTH, self.CARD_HEIGHT, self.BG_COLOR_TOP, self.BG_COLOR_BOT)
        draw = ImageDraw.Draw(img)

        font_title = self._get_font(64)
        font_big = self._get_font(96)
        font_medium = self._get_font(42)
        font_small = self._get_font(32)
        font_label = self._get_font(28)

        y = 80

        # Header
        draw.text((self.CARD_WIDTH // 2, y), "ASCEND MEDIA", fill=self.ACCENT, font=font_title, anchor="mt")
        y += 90
        draw.text((self.CARD_WIDTH // 2, y), f"{username}'s Stats", fill=self.TEXT_WHITE, font=font_medium, anchor="mt")
        y += 80

        # Divider
        draw.line([(100, y), (self.CARD_WIDTH - 100, y)], fill=self.ACCENT, width=3)
        y += 60

        # Total Watch Time
        total_hours = stats.get("total_hours", 0)
        draw.text((self.CARD_WIDTH // 2, y), "TOTAL WATCH TIME", fill=self.TEXT_GRAY, font=font_label, anchor="mt")
        y += 50
        draw.text((self.CARD_WIDTH // 2, y), f"{total_hours}h", fill=self.TEXT_GOLD, font=font_big, anchor="mt")
        y += 130

        # Sessions
        total_sessions = stats.get("total_sessions", 0)
        draw.text((self.CARD_WIDTH // 2, y), "SESSIONS", fill=self.TEXT_GRAY, font=font_label, anchor="mt")
        y += 50
        draw.text((self.CARD_WIDTH // 2, y), str(total_sessions), fill=self.TEXT_WHITE, font=font_big, anchor="mt")
        y += 130

        # Completed
        completed = stats.get("completed_count", 0)
        draw.text((self.CARD_WIDTH // 2, y), "COMPLETED", fill=self.TEXT_GRAY, font=font_label, anchor="mt")
        y += 50
        draw.text((self.CARD_WIDTH // 2, y), str(completed), fill=self.TEXT_WHITE, font=font_big, anchor="mt")
        y += 130

        # Streak
        streak = stats.get("streak", {})
        current_streak = streak.get("current", 0)
        longest_streak = streak.get("longest", 0)
        draw.text((self.CARD_WIDTH // 2, y), "WATCH STREAK", fill=self.TEXT_GRAY, font=font_label, anchor="mt")
        y += 50
        draw.text((self.CARD_WIDTH // 2, y), f"{current_streak} days", fill=self.TEXT_WHITE, font=font_medium, anchor="mt")
        y += 60
        draw.text((self.CARD_WIDTH // 2, y), f"Longest: {longest_streak} days", fill=self.TEXT_GRAY, font=font_small, anchor="mt")
        y += 80

        # Divider
        draw.line([(100, y), (self.CARD_WIDTH - 100, y)], fill=self.ACCENT, width=3)
        y += 60

        # Top Titles
        top_titles = stats.get("top_titles", [])
        if top_titles:
            draw.text((self.CARD_WIDTH // 2, y), "TOP WATCHED", fill=self.TEXT_GRAY, font=font_label, anchor="mt")
            y += 50
            for i, item in enumerate(top_titles[:5]):
                title_text = item.get("title", "Unknown")[:30]
                count = item.get("count", 0)
                medal = ["🥇", "🥈", "🥉", "4.", "5."][i] if i < 5 else f"{i+1}."
                line = f"{medal} {title_text} ({count}x)"
                draw.text((self.CARD_WIDTH // 2, y), line, fill=self.TEXT_WHITE, font=font_small, anchor="mt")
                y += 50

        y += 40

        # Skips
        total_skips = stats.get("total_skips", 0)
        saved_ms = stats.get("total_saved_ms", 0)
        saved_min = round(saved_ms / 60000, 1) if saved_ms else 0
        draw.text((self.CARD_WIDTH // 2, y), f"Skips: {total_skips} | Time Saved: {saved_min}m",
                   fill=self.TEXT_GRAY, font=font_small, anchor="mt")
        y += 60

        # Footer
        draw.text((self.CARD_WIDTH // 2, self.CARD_HEIGHT - 60),
                   f"Generated {time.strftime('%Y-%m-%d')} • Ascend Media RPC",
                   fill=(100, 100, 120), font=font_label, anchor="mt")

        buf = io.BytesIO()
        img.save(buf, format="PNG", quality=95)
        return buf.getvalue()
