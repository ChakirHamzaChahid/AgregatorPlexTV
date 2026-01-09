from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class Source(BaseModel):
    """Source de lecture (Fichier sur un serveur précis)."""
    server_name: str
    resolution: str
    is_owned: bool
    stream_url: str
    m3u_url: str
    plex_deeplink: str
    plex_web_url: str

class EpisodeDetail(BaseModel):
    """Détail d'un épisode."""
    id: str             # ex: "S01E01"
    index: int          # Numéro épisode
    title: str
    summary: str
    thumb_url: str = "" # Image spécifique de l'épisode
    sources: List[Source] = Field(default_factory=list)

class SeasonDetail(BaseModel):
    """Détail d'une saison."""
    index: int          # Numéro saison (1, 2...)
    title: str          # "Saison 1"
    episode_count: int
    episodes: List[EpisodeDetail] = Field(default_factory=list)

class MediaDetail(BaseModel):
    """Objet racine (Film ou Série)."""
    id: str
    type: str           # 'movie' ou 'show'
    title: str
    year: int
    director: str
    genres: List[str] = Field(default_factory=list)
    summary: str
    rating: float
    poster_url: str
    
    # Pour les films :
    sources: List[Source] = Field(default_factory=list)
    
    # Pour les séries :
    seasons: List[SeasonDetail] = Field(default_factory=list)

# Alias pour compatibilité avec le code existant si besoin
MovieDetail = MediaDetail 

class ServerInfo(BaseModel):
    name: str
    url: str
    owned: bool
    latency: float = 0.0
    status: str = "Online"