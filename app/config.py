import os
from pathlib import Path

class Settings:
    # --- Identifiants ---
    PLEX_TOKEN: str = os.getenv("PLEX_TOKEN", "yRS6nPz__19BvpuuPYX2")
    CLIENT_ID: str = os.getenv("CLIENT_ID", "PlexHub-Backend-VPerf")
    
    # --- Chemins ---
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    CACHE_DIR: Path = PROJECT_ROOT / "cache_assets"
    
    # --- Performance & Limites ---
    MAX_STREAMS: int = 3                # Max flux simultanés
    STREAM_CHUNK_SIZE: int = 1024 * 1024 * 2 # 2 Mo (Compromis Latence/CPU)
    
    # --- Optimisation Plex ---
    SCAN_TIMEOUT: int = 10              # Abandonne un serveur s'il ne répond pas en 10s
    SCAN_CACHE_TTL: int = 300           # 5 minutes de cache min avant d'autoriser un auto-refresh
    ONLY_OWNED: bool = False

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

settings = Settings()