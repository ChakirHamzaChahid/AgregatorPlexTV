import os
from pathlib import Path
from dotenv import load_dotenv

# Calcul du chemin absolu vers la racine du projet (là où est run.py et .env)
BASE_DIR = Path(__file__).resolve().parent.parent
env_path = BASE_DIR / ".env"

# Chargement explicite des variables d'environnement depuis .env
load_dotenv(dotenv_path=env_path)

class Settings:
    """
    Configuration globale de l'application chargée depuis les variables d'environnement.
    Centralise les paramètres de connexion, de performance et les constantes du projet.
    """
    
    # --- Identifiants & Sécurité ---
    # Token d'authentification Plex principal (X-Plex-Token)
    # Récupéré depuis l'environnement, indispensable pour communiquer avec l'API Plex.
    PLEX_TOKEN: str = os.getenv("PLEX_TOKEN", "") 
    
    # Identifiant unique de ce client agissant comme un "player" ou "proxy"
    CLIENT_ID: str = os.getenv("CLIENT_ID", "PlexHub-Chakir-Server")
    
    # --- Chemins Système ---
    # Racine du projet
    PROJECT_ROOT: Path = Path(__file__).parent.parent
    # Dossier de stockage des caches (images optimisées, DB temporaires, etc.)
    CACHE_DIR: Path = PROJECT_ROOT / "cache_assets"
    # Dossier de logs
    LOG_DIR: Path = PROJECT_ROOT / "logs"
    
    # --- Performance & Limites ---
    # Nombre maximum de flux de transcodage/streaming parallèles autorisés
    MAX_STREAMS: int = 3
    # Taille des chunks pour le streaming (2 Mo). 
    # Un buffer plus grand améliore la fluidité mais augmente l'usage RAM par worker.
    STREAM_CHUNK_SIZE: int = 1024 * 1024 * 2
    
    # --- Optimisation Plex ---
    # Temps d'attente max (en secondes) lors du test de connexion à un serveur
    SCAN_TIMEOUT: int = 10 
    # Durée de validité du cache de la bibliothèque avant le prochain scan automatique (5 min)
    SCAN_CACHE_TTL: int = 300
    # Si True, ne liste que les serveurs dont l'utilisateur est propriétaire (exclut les partagés)
    ONLY_OWNED: bool = False

    def __init__(self):
        """
        Initialisation de la configuration.
        S'assure que les répertoires nécessaires existent et valide les credentials critiques.
        """
        # Création automatique du dossier de cache au démarrage
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.LOG_DIR.mkdir(parents=True, exist_ok=True)

        
        # Log de démarrage pour valider la présence du token (masqué pour sécurité)
        if self.PLEX_TOKEN:
            token_preview = f"{self.PLEX_TOKEN[:4]}****"
            print(f"✅ [Config] Token chargé : {token_preview}")
        else:
            print("⚠️ [Config] AVERTISSEMENT : PLEX_TOKEN non trouvé ! L'application risque de ne pas fonctionner.")

# Instance unique de configuration à importer partout
settings = Settings()