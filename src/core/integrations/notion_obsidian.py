import logging
import os
import time
import requests
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger("stremio-rpc")


class NotionWatchLog:
    """Notion API integration for personal watch journal."""

    BASE_URL = "https://api.notion.com/v1"
    VERSION = "2022-06-28"

    def __init__(self, api_key: str = "", database_id: str = ""):
        self.api_key = api_key
        self.database_id = database_id

    def _headers(self) -> Dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Notion-Version": self.VERSION,
        }

    def create_entry(self, title: str, media_type: str = "movie",
                     season: int = 0, episode: int = 0,
                     rating: float = 0, notes: str = "",
                     image_url: str = "") -> bool:
        if not self.api_key or not self.database_id:
            return False
        try:
            properties = {
                "Title": {"title": [{"text": {"content": title}}]},
                "Type": {"select": {"name": media_type.title()}},
                "Date Watched": {"date": {"start": datetime.now().isoformat()}},
            }
            if season:
                properties["Season"] = {"number": season}
            if episode:
                properties["Episode"] = {"number": episode}
            if rating:
                properties["Rating"] = {"number": rating}

            children = []
            if notes:
                children.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [{"type": "text", "text": {"content": notes}}]
                    },
                })
            if image_url:
                children.append({
                    "object": "block",
                    "type": "image",
                    "image": {"type": "external", "external": {"url": image_url}},
                })

            payload = {
                "parent": {"database_id": self.database_id},
                "properties": properties,
            }
            if children:
                payload["children"] = children

            r = requests.post(
                f"{self.BASE_URL}/pages",
                json=payload,
                headers=self._headers(),
                timeout=10,
            )
            if r.status_code in (200, 201):
                logger.info(f"Notion watch log entry created: {title}")
                return True
            logger.warning(f"Notion create entry failed: {r.status_code}")
        except Exception as e:
            logger.error(f"Notion create entry error: {e}")
        return False


class ObsidianWatchLog:
    """Obsidian integration via local markdown files."""

    def __init__(self, vault_path: str = ""):
        self.vault_path = vault_path

    def create_entry(self, title: str, media_type: str = "movie",
                     season: int = 0, episode: int = 0,
                     rating: float = 0, notes: str = "",
                     image_url: str = "") -> bool:
        if not self.vault_path or not os.path.isdir(self.vault_path):
            return False
        try:
            watch_dir = os.path.join(self.vault_path, "Watch Log")
            os.makedirs(watch_dir, exist_ok=True)

            date_str = datetime.now().strftime("%Y-%m-%d")
            safe_title = "".join(c for c in title if c.isalnum() or c in " -_").strip()
            filename = f"{date_str} - {safe_title}.md"
            filepath = os.path.join(watch_dir, filename)

            content = f"---\n"
            content += f"title: \"{title}\"\n"
            content += f"type: {media_type}\n"
            content += f"date: {date_str}\n"
            if season:
                content += f"season: {season}\n"
            if episode:
                content += f"episode: {episode}\n"
            if rating:
                content += f"rating: {rating}\n"
            content += f"---\n\n"
            content += f"# {title}\n\n"
            if season and episode:
                content += f"**Season {season}, Episode {episode}**\n\n"
            if image_url:
                content += f"![Poster]({image_url})\n\n"
            if notes:
                content += f"## Notes\n\n{notes}\n"
            else:
                content += f"## Notes\n\n\n"

            with open(filepath, "w", encoding="utf-8") as f:
                f.write(content)

            logger.info(f"Obsidian watch log entry created: {filepath}")
            return True
        except Exception as e:
            logger.error(f"Obsidian create entry error: {e}")
        return False
