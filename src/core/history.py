
import json
import os
import time
from typing import List, Dict
from src.core.config import get_config_path
from src.core.encryption import EncryptionManager

HISTORY_FILE = os.path.join(get_config_path(), "history.enc")

class SkipHistory:
    def __init__(self, limit=100):
        self.crypto = EncryptionManager()
        self.limit = limit
        self.history: List[Dict] = self._load()

    def _load(self) -> List[Dict]:
        if not os.path.exists(HISTORY_FILE):
            return []
        try:
            with open(HISTORY_FILE, 'rb') as f:
                data = self.crypto.decrypt_data(f.read())
                return data if isinstance(data, list) else []
        except Exception as e:
            print(f"Error loading history: {e}")
            return []

    def save(self):
        try:
            encrypted = self.crypto.encrypt_data(self.history)
            with open(HISTORY_FILE, 'wb') as f:
                f.write(encrypted)
        except Exception as e:
            print(f"Error saving history: {e}")

    def add_entry(self, entry: Dict):
        """
        Entry structure:
        {
            "timestamp": int (unix),
            "title": str,
            "subtitle": str,
            "image_url": str,
            "type": str (intro/outro),
            "saved_str": str ("1m 20s"),
            "device": str
        }
        """
        # Add timestamp if missing
        if "timestamp" not in entry:
            entry["timestamp"] = int(time.time())

        # Prepend to list (newest first)
        self.history.insert(0, entry)
        
        # Enforce limit
        if len(self.history) > self.limit:
            self.history = self.history[:self.limit]
            
        self.save()

    def get_all(self):
        return self.history
