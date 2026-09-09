import json
import os
import sys
from typing import Optional


class SingleInstanceLock:
    """Process lock acquired before ADB and Discord resources are opened."""

    def __init__(self, directory: str, name: str = "ascend-media-rpc.lock"):
        self.path = os.path.join(os.path.abspath(directory), name)
        self.owner_path = self.path + ".owner.json"
        self._file = None
        self.owner: Optional[dict] = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        handle = open(self.path, "a+", encoding="utf-8")
        try:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                if handle.read(1) == "":
                    handle.seek(0)
                    handle.write(" ")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, BlockingIOError):
            handle.close()
            try:
                with open(self.owner_path, "r", encoding="utf-8") as reader:
                    raw = reader.read().strip()
                self.owner = json.loads(raw) if raw else None
            except Exception:
                self.owner = None
            return False

        self._file = handle
        self.owner = {
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "python": sys.executable,
        }
        # Windows denies reads that overlap a locked byte, so owner metadata
        # lives in a separate diagnostic file.
        with open(self.owner_path, "w", encoding="utf-8") as writer:
            json.dump(self.owner, writer)
        return True

    def release(self):
        if not self._file:
            return
        try:
            self._file.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._file.close()
            self._file = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Ascend Media RPC is already running")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
