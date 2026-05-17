
import os
import json
import base64
from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from src.core.config import get_config_path

KEY_FILE = os.path.join(get_config_path(), "security.key")

class EncryptionManager:
    def __init__(self):
        self.key = self._load_or_create_key()

    def _load_or_create_key(self):
        if os.path.exists(KEY_FILE):
            with open(KEY_FILE, 'rb') as f:
                return f.read()
        else:
            key = get_random_bytes(32) # AES-256
            with open(KEY_FILE, 'wb') as f:
                f.write(key)
            return key

    def encrypt_data(self, data: dict) -> bytes:
        """Encrypts dictionary to bytes"""
        json_bytes = json.dumps(data).encode('utf-8')
        nonce = get_random_bytes(12)
        cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
        ciphertext, tag = cipher.encrypt_and_digest(json_bytes)
        # Format: Nonce(12) + Tag(16) + Ciphertext
        return nonce + tag + ciphertext

    def decrypt_data(self, data_bytes: bytes) -> dict:
        """Decrypts bytes to dictionary"""
        try:
            nonce = data_bytes[:12]
            tag = data_bytes[12:28]
            ciphertext = data_bytes[28:]
            cipher = AES.new(self.key, AES.MODE_GCM, nonce=nonce)
            json_bytes = cipher.decrypt_and_verify(ciphertext, tag)
            return json.loads(json_bytes.decode('utf-8'))
        except Exception as e:
            print(f"Decryption Error: {e}")
            return {}
