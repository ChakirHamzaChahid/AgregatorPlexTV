import asyncio
import logging
import httpx
import urllib.parse
import sys
import io 
import os
import time
import sqlite3
from PIL import Image 
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, Response, HTTPException, APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List # Assure-toi d'avoir ces imports en haut

# Imports locaux
from app.config import settings
from app.models import MovieDetail, ServerInfo
from app.plex_client import plex_client
from app.discovery import discovery_service

# =============================================================================
# 1. HARDENING : SÉCURITÉ & LOGGING AVANCÉ
# =============================================================================

class TokenFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
        # On ne filtre que si le token est configuré et fait plus de 5 caractères
        if settings.PLEX_TOKEN and len(settings.PLEX_TOKEN) > 5 and settings.PLEX_TOKEN in msg:
            record.msg = msg.replace(settings.PLEX_TOKEN, "HIDDEN_TOKEN")
            record.args = ()
        return True

def setup_logging():
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
    
    formatter = logging.Formatter('%(asctime)s - %(name)-12s - %(levelname)-8s - %(message)s')
    
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(TokenFilter())
    root_logger.addHandler(console_handler)
    
    file_handler = RotatingFileHandler("server.log", maxBytes=10*1024*1024, backupCount=5, encoding='utf-8')
    file_handler.setFormatter(formatter)
    file_handler.addFilter(TokenFilter())
    root_logger.addHandler(file_handler)

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

timeout_config = httpx.Timeout(60.0, connect=30.0)
limits = httpx.Limits(max_keepalive_connections=settings.MAX_STREAMS + 2, max_connections=20)

http_client = httpx.AsyncClient(
    verify=False, 
    timeout=timeout_config, 
    limits=limits
)

stream_semaphore = asyncio.Semaphore(settings.MAX_STREAMS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Cycle de vie : Gestion du worker Maître avec verrouillage atomique."""
    # Petit délai aléatoire pour éviter que les workers ne frappent le port/fichier en même temps
    # Indispensable pour éviter WinError 10022
    await asyncio.sleep(0.1 * (os.getpid() % 10))
    lock_file = settings.CACHE_DIR / "server_start.lock"
    is_master_worker = False

    try:
        # Tentative d'ouverture exclusive ('x') : atomique au niveau OS
        try:
            settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            # Si le fichier existe, cette ligne lève une FileExistsError immédiatement
            with open(lock_file, "x") as f:
                f.write(str(os.getpid()))
            is_master_worker = True
        except FileExistsError:
            # Le fichier existe déjà, un autre worker est déjà maître
            # On vérifie si le verrou n'est pas périmé (plus de 5 min)
            if time.time() - lock_file.stat().st_mtime > 300:
                try:
                    lock_file.unlink() # On tente de supprimer le verrou mort
                    logger.warning("🧹 Ancien verrou expiré supprimé.")
                    # On ne se proclame pas maître tout de suite pour éviter un nouveau conflit
                except: pass
            is_master_worker = False

        if is_master_worker:
            logger.info(f"🚀 [Worker {os.getpid()}] ÉLU MAÎTRE - Initialisation unique")
            # Un seul démarrage de service
            asyncio.create_task(plex_client.refresh_library(force=True))
            discovery_service.start()
        else:
            logger.info(f"😴 [Worker {os.getpid()}] Worker Esclave - Mode passif")

        yield

    finally:
        # Seul le maître nettoie son verrou
        if is_master_worker:
            logger.info(f"🛑 Arrêt du Worker Maître ({os.getpid()})")
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except: pass
            discovery_service.stop()
        await http_client.aclose()

app = FastAPI(title="PlexHub Backend", lifespan=lifespan)
# 1. Ajout du CORS pour vos 2 Frontends (Web & Android TV)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Autorise toutes les origines pour le dev multi-plateforme
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. Conservation de votre compression GZip
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(GZipMiddleware, minimum_size=1000)

api_router = APIRouter(prefix="/api")

# =============================================================================
# 3. HARDENING : GESTIONNAIRE D'ERREURS GLOBAL
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ CRASH API NON GÉRÉ sur {request.url}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne critique du serveur. Consultez server.log."},
    )

# =============================================================================
# 4. ROUTES API REST (VERSION SQLITE + MONITORING)
# =============================================================================

@api_router.get("/servers", response_model=list[ServerInfo])
async def get_servers():
    """Liste des serveurs connectés (via SQLite)."""
    return plex_client.get_connected_servers()

@api_router.get("/movies", response_model=list[MovieDetail])
async def get_movies(
    request: Request,
    page: Optional[int] = None,  # Optionnel : Si None, on renvoie tout (Mode Web)
    size: Optional[int] = None,  # Optionnel : Si None, on renvoie tout (Mode Web)
    type: Optional[str] = None,
    sort: str = "added_at",
    order: str = "desc",
    search: Optional[str] = None
):
    """
    API Hybride :
    - Si page/size présents : Pagination SQL optimisée + Mode "Léger" (Pour Android TV).
    - Si page/size absents : Renvoie TOUT le catalogue + Mode "Complet" (Pour Web App existante).
    """
    start_time = time.time()
    base_url = ""
    
    movies_dict = plex_client.get_all_media()
    movies = list(movies_dict.values())
    
    # On détermine si on est en mode Android (pagination active)
    is_android_mode = page is not None and size is not None

    # 1. Construction de la requête SQL
    query = "SELECT data FROM media_v2 WHERE 1=1"
    params = []
    
    # Filtres (Type et Recherche s'appliquent aux deux modes)
    if type:
        query += " AND type = ?"
        params.append(type)
    
    if search:
        query += " AND title LIKE ?"
        params.append(f"%{search}%")

    # Tri SQL
    valid_sorts = {"added_at": "added_at", "title": "title", "year": "year", "rating": "rating"}
    sort_col = valid_sorts.get(sort, "added_at")
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"
    
    query += f" ORDER BY {sort_col} {sort_dir}"

    # PAGINATION CONDITIONNELLE
    # On n'ajoute LIMIT que si c'est demandé (Android TV)
    if is_android_mode:
        offset = (page - 1) * size
        query += " LIMIT ? OFFSET ?"
        params.extend([size, offset])

    results = []
    
    try:
        with sqlite3.connect(plex_client.db_path) as conn:
            cursor = conn.execute(query, params)
            
            for row in cursor:
                # Désérialisation rapide
                m_copy = MovieDetail.model_validate_json(row[0])
                
                # --- LOGIQUE DE RETOUR ---
                
                # A. Injection URL Poster (Commun)
                if m_copy.poster_url and m_copy.poster_url.startswith("/"):
                    m_copy.poster_url = base_url + m_copy.poster_url
                
                # B. Gestion de la charge utile (Hybride)
                if is_android_mode:
                    # MODE ANDROID : On allège l'objet au maximum pour la RAM de la TV
                    m_copy.seasons = []
                    m_copy.sources = []
                    # On ne traite que le strict nécessaire pour la grille (Poster)
                    if m_copy.poster_url.startswith("/"):
                         m_copy.poster_url = base_url + m_copy.poster_url
                
                else:
                    # MODE WEB (Legacy) : On garde tout et on injecte les URLs complètes
                    # C'est la logique originale de votre main.py pour l'app Web
                    # Injection URL Poster
                    if m_copy.poster_url.startswith("/"):
                        m_copy.poster_url = base_url + m_copy.poster_url
                    # URLs Sources Film
                    new_sources = []
                    for s in m_copy.sources:
                        s_copy = s.model_copy()
                        if s_copy.stream_url.startswith("/"):
                            s_copy.stream_url = base_url + s_copy.stream_url
                        if s_copy.m3u_url and s_copy.m3u_url.startswith("/"):
                            s_copy.m3u_url = base_url + s_copy.m3u_url
                        new_sources.append(s_copy)
                    m_copy.sources = new_sources
                    
                    # URLs Séries / Saisons / Épisodes
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
                
    except Exception as e:
        logger.error(f"❌ Erreur SQL get_movies: {e}")
        return []

    duration = time.time() - start_time
    mode_label = "ANDROID (Paginé)" if is_android_mode else "WEB (Complet)"
    logger.info(f"🚀 [{mode_label}] {len(results)} items | ⏱️ {duration:.4f}s")
    
    return results

@api_router.get("/movies/{movie_id}", response_model=MovieDetail)
async def get_movie_detail(movie_id: str, request: Request):
    """Détail d'un élément spécifique via SQLite."""
    movies = plex_client.get_all_media()
    movie = movies.get(movie_id)
    
    if not movie:
        logger.warning(f"🔍 [Worker {os.getpid()}] Média {movie_id} non trouvé")
        raise HTTPException(status_code=404, detail="Média introuvable")
    
    base_url = str(request.base_url).rstrip('/')
    m_copy = movie.model_copy()
    
    if m_copy.poster_url.startswith("/"):
        m_copy.poster_url = base_url + m_copy.poster_url
        
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
    
    logger.info(f"🔄 [Worker {os.getpid()}] Déclenchement scan manuel")
    background_tasks.add_task(plex_client.refresh_library, force=True)
    return {"message": "Scan démarré", "status": "accepted"}

app.include_router(api_router)

# =============================================================================
# 5. ROUTES FRONTEND & UTILS
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception as e:
        logger.error(f"Erreur Template: {e}")
        return "<h1>Erreur : Template index.html manquant</h1>"

@app.get("/proxy-image")
async def proxy_image(url: str, thumb: str, token: str):
    if not thumb: return Response(status_code=404)
    # Sécurité : On utilise le token de la config si celui fourni est vide
    token_to_use = token if token else settings.PLEX_TOKEN

    safe_name = thumb.strip("/").replace("/", "_").replace("\\", "_").replace(":", "") + ".webp"
    cache_path = settings.CACHE_DIR / safe_name
    
    browser_cache_headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "Access-Control-Allow-Origin": "*"
    }

    if cache_path.exists():
        return FileResponse(cache_path, headers=browser_cache_headers)

    try:
        full_url = f"{url}{thumb}?X-Plex-Token={token}"
        # CORRECTION ICI : On utilise directement await sur le client
        resp = await http_client.get(full_url)
        
        if resp.status_code == 200:
            img_content = resp.content # On récupère le contenu binaire
            
            # Optimisation Pillow avec conversion WebP
            with Image.open(io.BytesIO(img_content)) as img:
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                
                target_width = 400
                if img.width > target_width:
                    ratio = target_width / float(img.width)
                    target_height = int(float(img.height) * float(ratio))
                    img = img.resize((target_width, target_height), Image.LANCZOS)
                
                img.save(cache_path, "WEBP", quality=80, method=6)
            
            logger.info(f"🖼️ [Worker {os.getpid()}] Image optimisée : {safe_name}")
            return FileResponse(cache_path, headers=browser_cache_headers)
            
    except Exception as e:
        logger.error(f"❌ Erreur Proxy Image: {e}")
        
    return Response(status_code=404)

# =============================================================================
# 6. STREAMING ROBUSTE & PLAYLISTS
# =============================================================================

@app.get("/playlist/{play_id}.m3u")
async def get_playlist(play_id: str, server: str, path: str, token: str, title: str = "Video", request: Request = None):
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
    base_plex = server.rstrip('/')
    headers = plex_client.get_chrome_headers(token, play_id)
    
    if stream_semaphore.locked():
        logger.warning(f"⛔ [Worker {os.getpid()}] Rejet stream {play_id} : Slots pleins")
        raise HTTPException(status_code=503, detail="Serveur saturé")

    params_opti = {
        "path": path, "mediaIndex": 0, "partIndex": 0, "protocol": "http", 
        "offset": 0, "fastSeek": 1, "directPlay": 0, "directStream": 1, 
        "autoAdjustQuality": 1, "videoQuality": 60, "videoResolution": "1280x720", 
        "maxVideoBitrate": "4000", "videoCodec": "h264", "audioCodec": "aac", 
        "session": play_id, "X-Plex-Token": token, "copyts": 1, "X-Plex-Incomplete-Segments": 1
    }

    params_fallback = {
        "path": path, "mediaIndex": 0, "partIndex": 0, "protocol": "http",
        "offset": 0, "fastSeek": 1, "directPlay": 1, "directStream": 1,
        "session": play_id, "X-Plex-Token": token, "copyts": 1
    }

    async def iter_file():
        # Sécurité : Utilisation du token configuré si absent de l'URL
        token_to_use = token if token else settings.PLEX_TOKEN
        
        
        try:
            await stream_semaphore.acquire()
            logger.info(f"▶️ [Worker {os.getpid()}] START Stream {play_id}")
            use_fallback = False
            # CORRECTION : Utilisation directe de stream() sans 'async with' manuel sur le client
            # httpx.stream est lui-même un gestionnaire de contexte asynchrone
            try:
                async with http_client.stream("GET", f"{base_plex}/video/:/transcode/universal/start", 
                                            params=params_opti, headers=headers) as r:
                    if r.status_code == 200:
                        async for chunk in r.aiter_bytes(chunk_size=settings.STREAM_CHUNK_SIZE):
                            yield chunk
                    else:
                        logger.warning(f"⚠️ [Worker {os.getpid()}] Transcode 720p refusé (Code {r.status_code})")
                        use_fallback = True
            except Exception as e:
                logger.error(f"❌ Erreur stream opti: {e}")
                use_fallback = True

            if use_fallback:
                async with http_client.stream("GET", f"{base_plex}/video/:/transcode/universal/start", params=params_fallback, headers=headers) as r:
                    if r.status_code == 200:
                        logger.info(f"✅ [Worker {os.getpid()}] Stream Direct Play OK")
                        async for chunk in r.aiter_bytes(chunk_size=settings.STREAM_CHUNK_SIZE):
                            yield chunk
                        
        except Exception as e:
            logger.error(f"❌ [Worker {os.getpid()}] Erreur Critique Stream {play_id}: {e}")
        finally:
            stream_semaphore.release()
            logger.info(f"⏹️ [Worker {os.getpid()}] END Stream {play_id}")

    return StreamingResponse(
        iter_file(), 
        media_type="video/x-matroska",
        headers={"Content-Disposition": f"inline; filename=stream_{play_id}.mkv"}
    )