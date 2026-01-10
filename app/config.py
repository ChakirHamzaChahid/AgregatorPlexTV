import os
from pathlib import Path
from dotenv import load_dotenv

# Calcul du chemin absolu vers la racine du projet (là où est run.py et .env)
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

# Chargement explicite
load_dotenv(dotenv_path=env_path)

class Settings:
   # --- Identifiants ---
    # On ne met plus de valeur par défaut "secrète"
    # Si la variable n'existe pas, l'app pourra lever une erreur ou rester vide
    PLEX_TOKEN: str = os.getenv("PLEX_TOKEN", "") 

    def __init__(self):
        # Débug : Vérifie si le token est bien chargé (affiche les 4 premiers caractères)
        if self.PLEX_TOKEN:
            print(f"✅ Token chargé : {self.PLEX_TOKEN[:4]}****")
        else:
            print("❌ ERREUR : PLEX_TOKEN non trouvé dans l'environnement !")

    CLIENT_ID: str = os.getenv("CLIENT_ID", "PlexHub-Chakir-Server")
    
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