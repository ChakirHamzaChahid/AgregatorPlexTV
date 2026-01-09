from pydantic import BaseModel, Field
from typing import List, Optional

class MovieSource(BaseModel):
    """Source unique d'un média."""
    server_name: str
    resolution: str
    is_owned: bool
    stream_url: str      # Lecture directe JSON/Browser
    m3u_url: str         # <--- NOUVEAU : Lien Playlist pour lecteurs externes
    plex_deeplink: str
    plex_web_url: str

class MovieDetail(BaseModel):
    """Agrégation d'un média (Film ou Série)."""
    id: str
    type: str = "movie"  # <--- NOUVEAU : 'movie' ou 'show'
    title: str
    year: int
    director: str
    genres: List[str] = Field(default_factory=list)
    summary: str
    rating: float
    poster_url: str
    sources: List[MovieSource] = Field(default_factory=list)

class ServerInfo(BaseModel):
    name: str
    url: str
    owned: bool
    latency: float = 0.0
    status: str = "Online"