import asyncio
import logging
import httpx
import urllib.parse
import sys
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, Response, HTTPException, APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

# Imports locaux (Architecture Modulaire)
from app.config import settings
from app.models import MovieDetail, ServerInfo
from app.plex_client import plex_client
from app.discovery import discovery_service

# =============================================================================
# 1. HARDENING : SÉCURITÉ & LOGGING AVANCÉ
# =============================================================================

class TokenFilter(logging.Filter):
    """
    Filtre de sécurité qui masque le Token Plex dans les logs.
    Transforme 'token=xyz' en 'token=******'.
    """
    def filter(self, record):
        msg = record.getMessage()
        if settings.PLEX_TOKEN in msg:
            # On remplace le vrai token par une version masquée
            record.msg = msg.replace(settings.PLEX_TOKEN, "HIDDEN_TOKEN")
            record.args = () # On vide les args pour éviter que le formatage ne remette le token
        return True

def setup_logging():
    """Configure un système de log robuste (Console + Fichier Rotatif) pour TOUTE l'app."""
    # 1. On récupère le Logger RACINE (Root) pour tout capturer
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Nettoyage des handlers existants (pour éviter les doublons lors du reload)
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    
    # 2. Format des logs (Plus précis avec le nom du module)
    # Ex: 2023-10-25 12:00:00 - PlexClient - INFO - Scan terminé
    formatter = logging.Formatter('%(asctime)s - %(name)-12s - %(levelname)-8s - %(message)s')
    
    # 3. Handler Console
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(TokenFilter())
    root_logger.addHandler(console_handler)
    
    # 4. Handler Fichier (server.log)
    # Capture PlexClient, API, Discovery... TOUT.
    file_handler = RotatingFileHandler("server.log", maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.addFilter(TokenFilter())
    root_logger.addHandler(file_handler)

    # 5. Silence radio pour les librairies externes bavardes
    logging.getLogger("plexapi").setLevel(logging.CRITICAL)
    logging.getLogger("urllib3").setLevel(logging.CRITICAL)
    logging.getLogger("multipart").setLevel(logging.WARNING)
    logging.getLogger("watchfiles").setLevel(logging.WARNING)
    
    return logging.getLogger("API")

logger = setup_logging()
templates = Jinja2Templates(directory="app/templates")

# =============================================================================
# 2. CONFIGURATION HTTP & PERFORMANCE
# =============================================================================

# Timeouts généreux (60s) pour tolérer les serveurs distants lents
timeout_config = httpx.Timeout(60.0, connect=30.0)
# Limites pour éviter de saturer l'OS tout en permettant le streaming fluide
limits = httpx.Limits(max_keepalive_connections=settings.MAX_STREAMS + 2, max_connections=20)

http_client = httpx.AsyncClient(
    verify=False, 
    timeout=timeout_config, 
    limits=limits
)

# Sémaphore : Gestion des slots de streaming simultanés (ex: 3 max)
stream_semaphore = asyncio.Semaphore(settings.MAX_STREAMS)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie : Démarrage et Arrêt."""
    logger.info("🚀 Démarrage du serveur PlexHub (Version Prod)...")
    
    # 1. SCAN AU DÉMARRAGE (Background)
    # force=True : Lance le scan réseau même si le cache disque est chargé.
    # Assure que les nouvelles séries/films apparaissent rapidement.
    asyncio.create_task(plex_client.refresh_library(force=True))
    
    # 2. DÉCOUVERTE AUTO (mDNS)
    discovery_service.start()
    
    yield
    
    # Arrêt propre
    logger.info("🛑 Arrêt du serveur...")
    discovery_service.stop()
    await http_client.aclose()


app = FastAPI(title="PlexHub Backend", lifespan=lifespan)
api_router = APIRouter(prefix="/api")

# =============================================================================
# 3. HARDENING : GESTIONNAIRE D'ERREURS GLOBAL
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Capture toutes les erreurs non gérées pour éviter le crash complet."""
    logger.error(f"❌ CRASH API NON GÉRÉ sur {request.url}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne critique du serveur. Consultez server.log."},
    )

# =============================================================================
# 4. ROUTES API REST
# =============================================================================

@api_router.get("/servers", response_model=list[ServerInfo])
async def get_servers():
    """Liste des serveurs connectés."""
    return plex_client.connected_servers

@api_router.get("/movies", response_model=list[MovieDetail])
async def get_movies(request: Request):
    """
    API Principale : Retourne tout le contenu (Films & Séries).
    Injecte les URLs absolues pour l'affichage et la lecture.
    """
    base_url = str(request.base_url).rstrip('/')
    
    # Récupération ultra-rapide depuis la RAM (déjà formaté par plex_client)
    movies = list(plex_client.movies_cache.values())
    
    results = []
    for m in movies:
        m_copy = m.model_copy()
        
        # URL absolue pour l'affiche
        if m_copy.poster_url.startswith("/"):
            m_copy.poster_url = base_url + m_copy.poster_url
        
        # URLs absolues pour les sources (Lecture & M3U)
        new_sources = []
        for s in m_copy.sources:
            s_copy = s.model_copy()
            
            if s_copy.stream_url.startswith("/"):
                s_copy.stream_url = base_url + s_copy.stream_url
            
            if s_copy.m3u_url and s_copy.m3u_url.startswith("/"):
                s_copy.m3u_url = base_url + s_copy.m3u_url
                
            new_sources.append(s_copy)
        m_copy.sources = new_sources
        
        # Pour les séries, on doit aussi injecter les URLs dans les épisodes imbriqués
        if m_copy.type == 'show':
            for season in m_copy.seasons:
                for ep in season.episodes:
                    if ep.thumb_url and ep.thumb_url.startswith("/"):
                        ep.thumb_url = base_url + ep.thumb_url
                    
                    new_ep_sources = []
                    for s in ep.sources:
                        s_ep_copy = s.model_copy()
                        if s_ep_copy.stream_url.startswith("/"):
                            s_ep_copy.stream_url = base_url + s_ep_copy.stream_url
                        if s_ep_copy.m3u_url and s_ep_copy.m3u_url.startswith("/"):
                            s_ep_copy.m3u_url = base_url + s_ep_copy.m3u_url
                        new_ep_sources.append(s_ep_copy)
                    ep.sources = new_ep_sources

        results.append(m_copy)
            
    return results

@api_router.get("/movies/{movie_id}", response_model=MovieDetail)
async def get_movie_detail(movie_id: str, request: Request):
    """Détail d'un élément spécifique."""
    movie = plex_client.movies_cache.get(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Média introuvable")
    
    base_url = str(request.base_url).rstrip('/')
    m_copy = movie.model_copy()
    
    if m_copy.poster_url.startswith("/"):
        m_copy.poster_url = base_url + m_copy.poster_url
        
    # Injection URLs (copie de la logique ci-dessus pour le détail unique)
    new_sources = []
    for s in m_copy.sources:
        s_copy = s.model_copy()
        if s_copy.stream_url.startswith("/"):
            s_copy.stream_url = base_url + s_copy.stream_url
        if s_copy.m3u_url and s_copy.m3u_url.startswith("/"):
            s_copy.m3u_url = base_url + s_copy.m3u_url
        new_sources.append(s_copy)
    m_copy.sources = new_sources
    
    if m_copy.type == 'show':
        for season in m_copy.seasons:
            for ep in season.episodes:
                if ep.thumb_url and ep.thumb_url.startswith("/"):
                    ep.thumb_url = base_url + ep.thumb_url
                new_ep_sources = []
                for s in ep.sources:
                    s_ep_copy = s.model_copy()
                    if s_ep_copy.stream_url.startswith("/"):
                        s_ep_copy.stream_url = base_url + s_ep_copy.stream_url
                    if s_ep_copy.m3u_url and s_ep_copy.m3u_url.startswith("/"):
                        s_ep_copy.m3u_url = base_url + s_ep_copy.m3u_url
                    new_ep_sources.append(s_ep_copy)
                ep.sources = new_ep_sources
    
    return m_copy

@api_router.post("/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    """Déclenche un scan manuel (non-bloquant)."""
    if plex_client.is_scanning:
        return {"message": "Scan déjà en cours", "status": "busy"}
    
    background_tasks.add_task(plex_client.refresh_library, force=True)
    return {"message": "Scan démarré", "status": "accepted"}

app.include_router(api_router)


# =============================================================================
# 5. ROUTES FRONTEND & UTILS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Sert l'interface Web."""
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"Erreur Template: {e}")
        return "<h1>Erreur : Template index.html manquant</h1>"

@app.get("/proxy-image")
async def proxy_image(url: str, thumb: str, token: str):
    """Proxy d'images avec Cache Disque (Contourne CORS/Auth)."""
    if not thumb: return Response(status_code=404)
    
    safe_name = thumb.strip("/").replace("/", "_").replace("\\", "_").replace(":", "") + ".jpg"
    cache_path = settings.CACHE_DIR / safe_name
    
    # 1. Cache Disque (Prioritaire)
    if cache_path.exists():
        return FileResponse(cache_path)

    # 2. Téléchargement Plex (Si absent du cache)
    try:
        full_url = f"{url}{thumb}?X-Plex-Token={token}"
        async with http_client.stream("GET", full_url) as resp:
            if resp.status_code == 200:
                with open(cache_path, "wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
                return FileResponse(cache_path)
    except Exception:
        pass
        
    return Response(status_code=404)


# =============================================================================
# 6. STREAMING ROBUSTE & PLAYLISTS
# =============================================================================

@app.get("/playlist/{play_id}.m3u")
async def get_playlist(play_id: str, server: str, path: str, token: str, title: str = "Video", request: Request = None):
    """Génère une playlist M3U pour VLC/IPTV."""
    base_url = str(request.base_url).rstrip('/') if request else ""
    
    stream_url = (
        f"{base_url}/vlc-stream/{play_id}?"
        f"server={urllib.parse.quote(server)}&"
        f"path={urllib.parse.quote(path)}&"
        f"token={token}"
    )
    
    content = f"#EXTM3U\n#EXTINF:-1,{title}\n{stream_url}"
    return Response(content=content, media_type="application/x-mpegurl")


@app.get("/vlc-stream/{play_id}")
async def stream_video(play_id: str, server: str, path: str, token: str):
    """
    Proxy de Streaming Intelligent.
    Stratégie : Tente 720p (Léger) -> Si échec, tente Direct Play (Lourd mais compatible).
    """
    base_plex = server.rstrip('/')
    headers = plex_client.get_chrome_headers(token, play_id)
    
    if stream_semaphore.locked():
        logger.warning(f"⛔ Rejet stream {play_id} : Serveur plein")
        raise HTTPException(status_code=503, detail="Serveur saturé")

    # CONFIG 1 : OPTIMISÉE (720p / 4Mbps)
    params_opti = {
        "path": path, "mediaIndex": 0, "partIndex": 0, "protocol": "http", 
        "offset": 0, "fastSeek": 1, 
        "directPlay": 0, "directStream": 1, 
        "autoAdjustQuality": 1,
        "videoQuality": 60, "videoResolution": "1280x720", "maxVideoBitrate": "4000",
        "videoCodec": "h264", "audioCodec": "aac", 
        "session": play_id, "X-Plex-Token": token, "copyts": 1, "X-Plex-Incomplete-Segments": 1
    }

    # CONFIG 2 : FALLBACK (Direct Play / Qualité Originale)
    params_fallback = {
        "path": path, "mediaIndex": 0, "partIndex": 0, "protocol": "http",
        "offset": 0, "fastSeek": 1,
        "directPlay": 1, "directStream": 1,
        "session": play_id, "X-Plex-Token": token, "copyts": 1
    }

    async def iter_file():
        await stream_semaphore.acquire()
        logger.info(f"▶️ Stream START {play_id}")
        
        try:
            use_fallback = False
            
            # TENTATIVE 1 : 720p
            resp = await http_client.get(f"{base_plex}/video/:/transcode/universal/decision", params=params_opti, headers=headers)
            
            if resp.status_code != 200:
                logger.warning(f"⚠️ Transcodage refusé ({resp.status_code})...")
                use_fallback = True
            else:
                async with http_client.stream("GET", f"{base_plex}/video/:/transcode/universal/start", params=params_opti, headers=headers) as r:
                    if r.status_code == 200:
                        logger.info("✅ Streaming 720p OK")
                        async for chunk in r.aiter_bytes(chunk_size=settings.STREAM_CHUNK_SIZE):
                            yield chunk
                    else:
                        logger.warning(f"⚠️ Erreur Flux 720p ({r.status_code})...")
                        use_fallback = True

            # TENTATIVE 2 : Direct Play
            if use_fallback:
                logger.info("🔄 Bascule sur Direct Play (Secours)...")
                await asyncio.sleep(0.5)
                async with http_client.stream("GET", f"{base_plex}/video/:/transcode/universal/start", params=params_fallback, headers=headers) as r:
                    if r.status_code == 200:
                        logger.info("✅ Streaming Direct Play OK")
                        async for chunk in r.aiter_bytes(chunk_size=settings.STREAM_CHUNK_SIZE):
                            yield chunk
                    else:
                        logger.error(f"❌ ÉCHEC Streaming ({r.status_code})")
                        
        except Exception as e:
            logger.error(f"Erreur Stream: {e}")
        finally:
            stream_semaphore.release()
            logger.info(f"⏹️ Stream END {play_id}")

    return StreamingResponse(iter_file(), media_type="video/x-matroska")