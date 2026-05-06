import json
import os
from .logger import logger

class StatsManager:
    def __init__(self, stats_path="data/stats.json"):
        # Handle cases where the full config object is passed instead of a path
        if not isinstance(stats_path, str):
            self.stats_path = "data/stats.json"
        else:
            self.stats_path = stats_path
        self.data = {
            "skips": 0,
            "saved": 0,
            "trakt": 0
        }
        self.load()

    def load(self):
        if os.path.exists(self.stats_path):
            try:
                with open(self.stats_path, "r") as f:
                    self.data.update(json.load(f))
            except:
                logger.error("Failed to load stats")

    def save(self):
        os.makedirs(os.path.dirname(self.stats_path), exist_ok=True)
        try:
            with open(self.stats_path, "w") as f:
                json.dump(self.data, f)
        except:
            logger.error("Failed to save stats")

    def increment(self, key, amount=1):
        if key in self.data:
            self.data[key] += amount
            self.save()

    def get(self, key, default=0):
        return self.data.get(key, default)

    def set(self, key, value):
        self.data[key] = value
        self.save()
