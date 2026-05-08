import logging
import importlib
import os
from typing import Dict, List, Optional, Any
from abc import ABC, abstractmethod

logger = logging.getLogger("stremio-rpc")


class MetadataProvider(ABC):
    """Base interface for metadata providers (TMDB, AniList, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def search(self, title: str, year: Optional[int] = None) -> Optional[Dict]:
        pass

    @abstractmethod
    def get_details(self, media_id: str) -> Optional[Dict]:
        pass

    def get_artwork(self, media_id: str) -> Optional[str]:
        return None


class SkipProvider(ABC):
    """Base interface for skip segment providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def get_skip_times(self, imdb_id: str, season: int, episode: int,
                       tmdb_id: Optional[int] = None,
                       title: Optional[str] = None,
                       is_movie: bool = False) -> Optional[List[Dict]]:
        pass


class ScrobbleProvider(ABC):
    """Base interface for scrobble/tracking providers (Trakt, Simkl, etc.)."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def scrobble(self, action: str, media_data: Dict, progress: float) -> bool:
        pass

    def is_authenticated(self) -> bool:
        return False


class ArtworkProvider(ABC):
    """Base interface for artwork providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    def get_artwork(self, title: str, season: int = 0, episode: int = 0,
                    imdb_id: str = "", tmdb_id: int = 0) -> Optional[str]:
        pass


class PluginRegistry:
    """Central registry for all provider plugins."""

    def __init__(self):
        self._metadata_providers: Dict[str, MetadataProvider] = {}
        self._skip_providers: Dict[str, SkipProvider] = {}
        self._scrobble_providers: Dict[str, ScrobbleProvider] = {}
        self._artwork_providers: Dict[str, ArtworkProvider] = {}

    def register_metadata(self, provider: MetadataProvider):
        self._metadata_providers[provider.name] = provider
        logger.info(f"Plugin: Registered metadata provider '{provider.name}'")

    def register_skip(self, provider: SkipProvider):
        self._skip_providers[provider.name] = provider
        logger.info(f"Plugin: Registered skip provider '{provider.name}'")

    def register_scrobble(self, provider: ScrobbleProvider):
        self._scrobble_providers[provider.name] = provider
        logger.info(f"Plugin: Registered scrobble provider '{provider.name}'")

    def register_artwork(self, provider: ArtworkProvider):
        self._artwork_providers[provider.name] = provider
        logger.info(f"Plugin: Registered artwork provider '{provider.name}'")

    def get_metadata_provider(self, name: str) -> Optional[MetadataProvider]:
        return self._metadata_providers.get(name)

    def get_skip_provider(self, name: str) -> Optional[SkipProvider]:
        return self._skip_providers.get(name)

    def get_scrobble_provider(self, name: str) -> Optional[ScrobbleProvider]:
        return self._scrobble_providers.get(name)

    def get_artwork_provider(self, name: str) -> Optional[ArtworkProvider]:
        return self._artwork_providers.get(name)

    def list_providers(self) -> Dict[str, List[str]]:
        return {
            "metadata": list(self._metadata_providers.keys()),
            "skip": list(self._skip_providers.keys()),
            "scrobble": list(self._scrobble_providers.keys()),
            "artwork": list(self._artwork_providers.keys()),
        }

    def load_plugins_from_directory(self, plugin_dir: str):
        if not os.path.isdir(plugin_dir):
            return
        for filename in os.listdir(plugin_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                module_name = filename[:-3]
                try:
                    spec = importlib.util.spec_from_file_location(
                        module_name, os.path.join(plugin_dir, filename)
                    )
                    if spec and spec.loader:
                        module = importlib.util.module_from_spec(spec)
                        spec.loader.exec_module(module)
                        if hasattr(module, "register"):
                            module.register(self)
                            logger.info(f"Plugin: Loaded plugin '{module_name}'")
                except Exception as e:
                    logger.error(f"Plugin: Failed to load '{module_name}': {e}")
