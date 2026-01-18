from pydantic import BaseModel, Field
from typing import List, Optional, Dict
from datetime import datetime

class Source(BaseModel):
    """
    Source de lecture (Fichier sur un serveur précis).
    Représente une instance de média disponible sur un serveur Plex spécifique.
    """
    server_name: str    # Nom du serveur Plex hébergeant le fichier
    resolution: str     # Résolution vidéo (ex: "1080p", "4K", "SD")
    is_owned: bool      # Indique si le serveur appartient à l'utilisateur (True) ou est partagé (False)
    stream_url: str     # URL directe pour le streaming du fichier
    m3u_url: str        # URL formatée pour utilisation dans une playlist M3U
    plex_deeplink: str  # Lien profond (deep link) pour ouvrir le média dans l'application Plex native
    plex_web_url: str   # URL pour ouvrir le média dans l'interface web de Plex

class EpisodeDetail(BaseModel):
    """
    Détail d'un épisode d'une série TV.
    """
    id: str             # Identifiant unique composé (ex: "S01E01")
    index: int          # Numéro de l'épisode dans la saison
    title: str          # Titre de l'épisode
    summary: str        # Résumé / Synopsis de l'épisode
    thumb_url: str = "" # URL de l'image miniature (thumbnail) spécifique à l'épisode
    sources: List[Source] = Field(default_factory=list) # Liste des sources disponibles pour cet épisode

class SeasonDetail(BaseModel):
    """
    Détail d'une saison d'une série TV.
    """
    index: int          # Numéro de la saison (1, 2, ...)
    title: str          # Titre affiché de la saison (ex: "Saison 1")
    episode_count: int  # Nombre total d'épisodes dans la saison
    episodes: List[EpisodeDetail] = Field(default_factory=list) # Liste des épisodes contenus dans la saison


# class CastMember(BaseModel):
#     name: str           # Nom de l'acteur
#     role: str           # Rôle joué
#     thumb_url: Optional[str] = None # URL de la photo

class AudioTrack(BaseModel):
    display_title: str  # Titre affiché (ex: "English (AC3 5.1)")
    language: str       # Code langue (ex: "en")
    codec: str          # Codec audio (ex: "ac3", "aac")
    channels: int       # Nombre de canaux (ex: 6)
    forced: bool        # Piste forcée ?

class Subtitle(BaseModel):
    display_title: str  # Titre affiché
    language: str       # Code langue
    codec: str          # Format (ex: "srt", "pgs")
    forced: bool        # Sous-titre forcé ?

class Collection(BaseModel):
    title: str          # Titre de la collection
    key: str            # Clé Plex /collections/123
    thumb_url: Optional[str] = None
    child_count: int = 0

class Marker(BaseModel):
    title: str = "Marker" # Intro / Credits
    type: str           # 'intro' ou 'credits'
    start_time: int     # ms
    end_time: int       # ms

class SimilarItem(BaseModel):
    id: str             # ID du média similaire
    title: str
    year: int
    thumb_url: Optional[str] = None
    rating: float = 0.0

class Chapter(BaseModel):
    title: str          # Titre du chapitre
    start_time: int     # Début en millisecondes
    end_time: int       # Fin en millisecondes
    thumb_url: Optional[str] = None

class Trailer(BaseModel):
    title: str          # Titre du trailer
    duration: int       # Durée en ms
    thumb_url: Optional[str] = None
    stream_url: Optional[str] = None  # Lien de lecture
    key: Optional[str] = None

class HistoryEntry(BaseModel):
    id: str             # ID du média
    title: str
    type: str           # 'movie' ou 'show'
    watched_at: datetime  # Date du visionnage
    view_offset: int = 0
    duration: int = 0
    thumb_url: Optional[str] = None

class ClientInfo(BaseModel):
    name: str           # Nom du client
    device_class: str   # Type (stb, tablet, phone, etc.)
    platform: str       # Plateforme (iOS, Android, etc.)
    is_available: bool  # Connecté
    is_playing: bool = False

class SessionInfo(BaseModel):
    user: str           # Utilisateur regardant
    media_title: str
    media_type: str     # 'movie' ou 'show'
    progress_percent: float  # 0-100
    view_offset: int    # Position en ms
    duration: int       # Durée totale en ms
    client_name: str    # Appareil de lecture

class MediaDetail(BaseModel):
    """
    Objet racine représentant un média (Film ou Série).
    Contient toutes les métadonnées et les liens vers les fichiers ou épisodes.
    """
    id: str             # Identifiant unique du média (ratingKey Plex ou autre ID interne)
    type: str           # Type de média : 'movie' pour film ou 'show' pour série
    title: str          # Titre du média
    year: int           # Année de sortie
    added_at: datetime  # Date d'ajout à la bibliothèque
    studio: Optional[str] = None         # Studio de production
    content_rating: Optional[str] = None # Classification du contenu (ex: PG-13, TV-MA)
    director: Optional[str] = None       # Réalisateur (pertinent surtout pour les films)
    genres: List[str] = Field(default_factory=list) # Liste des genres associés
    summary: str        # Résumé global / Synopsis
    rating: float = 0.0 # Note générale Plex (sur 10)
    imdb_rating: Optional[float] = None  # Note issue d'IMDB
    rotten_rating: Optional[int] = None  # Score Rotten Tomatoes (souvent en %)
    poster_url: str     # URL de l'affiche (poster)
    backdrop_url: Optional[str] = None   # URL de l'arrière-plan (fanart)
    
    # Enrichissements
    runtime: int = 0                     # Durée en minutes
    # cast: List[CastMember] = Field(default_factory=list)
    badges: List[str] = Field(default_factory=list) # Tags techniques (4K, HDR, Atmos...)
    labels: List[str] = Field(default_factory=list) # Tags personnalisés (Favoris, 4K, etc.)
    audio_tracks: List[AudioTrack] = Field(default_factory=list)
    subtitles: List[Subtitle] = Field(default_factory=list)
    chapters: List[Chapter] = Field(default_factory=list)
    trailers: List[Trailer] = Field(default_factory=list) # Trailers disponibles
    
    # Advanced
    markers: List[Marker] = Field(default_factory=list)
    similar: List[SimilarItem] = Field(default_factory=list)
    view_offset: int = 0  # Progression en ms
    view_count: int = 0   # Nombre de vues (0 = Non vu)
    last_viewed_at: Optional[datetime] = None  # Dernière date de visionnage
    
    # Pour les films : Liste des sources directes
    sources: List[Source] = Field(default_factory=list)
    
    # Pour les séries : Liste des saisons (qui contiennent les épisodes et leurs sources)
    seasons: List[SeasonDetail] = Field(default_factory=list)

# Alias pour compatibilité avec le code existant si besoin
MovieDetail = MediaDetail 

class ServerInfo(BaseModel):
    """
    Informations d'état d'un serveur Plex connecté.
    """
    name: str           # Nom du serveur
    url: str            # Adresse URL du serveur
    owned: bool         # Indique si le serveur appartient à l'utilisateur actuel
    latency: float = 0.0 # Latence réseau mesurée (en ms)
    status: str = "Online" # Statut de disponibilité ("Online", "Offline", "Unreachable")
    version: Optional[str] = None  # Version Plex Media Server
    plex_pass: bool = False  # Plex Pass actif
    transcoder_available: bool = False  # Transcodeur vidéo disponible
    active_activities: List[str] = Field(default_factory=list)  # Scans, indexations en cours