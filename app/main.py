import asyncio
import logging
import httpx
import urllib.parse
import sys
import io 
import os
import time
import sqlite3
import json
from PIL import Image 
from logging.handlers import RotatingFileHandler
from fastapi import FastAPI, Request, Response, HTTPException, APIRouter, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta

# Imports locaux
from app.config import settings
from app.models import MovieDetail, ServerInfo
from app.plex_client import plex_client
from app.discovery import discovery_service

# =============================================================================
# 1. HARDENING : CACHE PARTAGÉ & LOGGING
# =============================================================================

# ===== SHARED SQLITE CACHE (Robust & Multi-Worker Safe) =====
class SharedSqliteCache:
    def __init__(self, db_path):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS api_cache (
                        key TEXT PRIMARY KEY,
                        data TEXT,
                        expires_at REAL
                    )
                """)
        except Exception as e:
            print(f"Cache DB Init Error: {e}")

    def get(self, key: str) -> Optional[List[Dict]]:
        try:
            # CORRECTION CRITIQUE : Mode Lecture Seule (RO) pour éviter les verrous
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, timeout=5) as conn:
                cursor = conn.execute(
                    "SELECT data FROM api_cache WHERE key = ? AND expires_at > ?", 
                    (key, time.time())
                )
                row = cursor.fetchone()
                if row:
                    return json.loads(row[0])
        except: pass
        return None
    
    def set(self, key: str, value: List[Any], ttl_seconds: int = 300) -> None:
        try:
            json_data = json.dumps([item.model_dump() for item in value])
            expires = time.time() + ttl_seconds
            
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO api_cache (key, data, expires_at) VALUES (?, ?, ?)",
                    (key, json_data, expires)
                )
        except Exception as e:
            print(f"Cache Set Error: {e}")
    
    def clear(self) -> None:
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("DELETE FROM api_cache")
        except: pass
    
    def stats(self) -> Dict[str, int]:
        try:
            # Lecture seule pour les stats aussi
            with sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True) as conn:
                count = conn.execute("SELECT COUNT(*) FROM api_cache").fetchone()[0]
                return {"cached_keys": count}
        except: return {"error": "db_error"}

# Initialisation du cache
_api_cache = SharedSqliteCache(settings.CACHE_DIR / "http_cache.db")

class TokenFilter(logging.Filter):
    def filter(self, record):
        msg = record.getMessage()
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
# 2. CONFIGURATION HTTP & LIFECYCLE
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
    await asyncio.sleep(0.1 * (os.getpid() % 10))
    lock_file = settings.CACHE_DIR / "server_start.lock"
    is_master_worker = False

    try:
        try:
            settings.CACHE_DIR.mkdir(parents=True, exist_ok=True)
            with open(lock_file, "x") as f:
                f.write(str(os.getpid()))
            is_master_worker = True
        except FileExistsError:
            if time.time() - lock_file.stat().st_mtime > 1200:
                try:
                    lock_file.unlink()
                    logger.warning("🧹 Ancien verrou expiré supprimé.")
                except: pass
            is_master_worker = False

        if is_master_worker:
            logger.info(f"🚀 [Worker {os.getpid()}] ÉLU MAÎTRE - Initialisation unique")
            
            # CORRECTION CRITIQUE : NE PAS VIDER LE CACHE AU DÉMARRAGE !
            # _api_cache.clear() <--- Commenté pour garder la persistance après un crash/restart
            
            # CORRECTION CRITIQUE : force=False pour respecter le cooldown anti-spam
            asyncio.create_task(plex_client.refresh_library(force=False))
            
            discovery_service.start()
        else:
            logger.info(f"😴 [Worker {os.getpid()}] Worker Esclave - Mode passif")

        yield

    finally:
        if is_master_worker:
            logger.info(f"🛑 Arrêt du Worker Maître ({os.getpid()})")
            if lock_file.exists():
                try:
                    lock_file.unlink()
                except: pass
            discovery_service.stop()
        await http_client.aclose()

app = FastAPI(title="PlexHub Backend", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

api_router = APIRouter(prefix="/api")

# =============================================================================
# 3. ROUTES API REST (OPTIMISÉES)
# =============================================================================

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"❌ CRASH API NON GÉRÉ sur {request.url}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Erreur interne critique du serveur. Consultez server.log."},
    )

@api_router.get("/servers", response_model=list[ServerInfo])
async def get_servers():
    return plex_client.get_connected_servers()

@api_router.get("/movies", response_model=list[MovieDetail])
async def get_movies(
    request: Request,
    page: Optional[int] = None,
    size: Optional[int] = None,
    type: Optional[str] = None,
    sort: str = "added_at",
    order: str = "desc",
    search: Optional[str] = None
):
    start_time = time.time()
    is_android_mode = page is not None and size is not None
    
    # 1. CACHE PERSISTANT (SQLite)
    cache_key = f"movies_{page}_{size}_{type}_{sort}_{order}_{search}"
    cached_data = _api_cache.get(cache_key)
    
    if cached_data is not None:
        logger.info(f"✅ CACHE HIT: {cache_key}")
        # On reconstruit les objets Pydantic depuis les dicts du cache
        return [MovieDetail(**item) for item in cached_data]

    logger.info(f"❌ CACHE MISS: {cache_key}")

    # 2. SQL : Construction requête
    query = "SELECT data FROM media_v2 WHERE 1=1"
    params = []
    
    if type:
        query += " AND type = ?"
        params.append(type)
    
    if search and search.strip():
        query += " AND (title LIKE ? OR summary LIKE ?)"
        search_param = f"%{search}%"
        params.extend([search_param, search_param])

    valid_sorts = {"added_at": "added_at", "title": "title", "year": "year", "rating": "rating"}
    sort_col = valid_sorts.get(sort, "added_at")
    sort_dir = "ASC" if order.lower() == "asc" else "DESC"
    query += f" ORDER BY {sort_col} {sort_dir}, title ASC"

    if is_android_mode:
        offset = (page - 1) * size
        query += " LIMIT ? OFFSET ?"
        params.extend([size, offset])

    results = []
    base_url = "" 

    try:
        with sqlite3.connect(plex_client.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(query, params)
            
            for row in cursor:
                try:
                    m = MovieDetail.model_validate_json(row['data'])
                    
                    # Logique Métier
                    if m.poster_url and m.poster_url.startswith("/"):
                        m.poster_url = base_url + m.poster_url
                    
                    if is_android_mode:
                        m.seasons = []
                        m.sources = []
                    else:
                        for s in m.sources:
                            if s.stream_url.startswith("/"):
                                s.stream_url = base_url + s.stream_url
                            if s.m3u_url and s.m3u_url.startswith("/"):
                                s.m3u_url = base_url + s.m3u_url
                        
                        if m.type == 'show':
                            for season in m.seasons:
                                for ep in season.episodes:
                                    if ep.thumb_url and ep.thumb_url.startswith("/"):
                                        ep.thumb_url = base_url + ep.thumb_url
                                    for s_ep in ep.sources:
                                        if s_ep.stream_url.startswith("/"):
                                            s_ep.stream_url = base_url + s_ep.stream_url
                                        if s_ep.m3u_url and s_ep.m3u_url.startswith("/"):
                                            s_ep.m3u_url = base_url + s_ep.m3u_url
                    results.append(m)
                except Exception as e:
                    logger.error(f"❌ Failed to process row: {e}")
                    continue

    except Exception as e:
        logger.error(f"❌ SQL Error: {e}")
        raise HTTPException(status_code=500, detail="Database error")
    
    # 3. SAUVEGARDE CACHE
    _api_cache.set(cache_key, results, ttl_seconds=300)
    
    duration = time.time() - start_time
    mode_lbl = "ANDROID" if is_android_mode else "WEB"
    logger.info(f"🚀 [{mode_lbl}] {len(results)} items | ⏱️ {duration:.4f}s")
    
    return results

@api_router.get("/movies/{movie_id}", response_model=MovieDetail)
async def get_movie_detail(movie_id: str, request: Request):
    base_url = ""
    try:
        with sqlite3.connect(plex_client.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT data FROM media_v2 WHERE id = ?", (movie_id,))
            row = cursor.fetchone()
            
            if not row:
                logger.warning(f"🔍 Média {movie_id} non trouvé")
                raise HTTPException(status_code=404, detail="Média introuvable")
            
            m = MovieDetail.model_validate_json(row['data'])
            
            if m.poster_url and m.poster_url.startswith("/"):
                m.poster_url = base_url + m.poster_url
                
            new_sources = []
            for s in m.sources:
                s_copy = s.model_copy()
                if s_copy.stream_url.startswith("/"):
                    s_copy.stream_url = base_url + s_copy.stream_url
                if s_copy.m3u_url and s_copy.m3u_url.startswith("/"):
                    s_copy.m3u_url = base_url + s_copy.m3u_url
                new_sources.append(s_copy)
            m.sources = new_sources
            
            if m.type == 'show':
                for season in m.seasons:
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
            return m
    except HTTPException: raise
    except Exception as e:
        logger.error(f"❌ Error getting detail for {movie_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error")

@api_router.get("/cache/stats")
async def get_cache_stats():
    return {"cache_stats": _api_cache.stats(), "timestamp": datetime.now().isoformat()}

@api_router.post("/cache/clear")
async def clear_cache():
    _api_cache.clear()
    logger.info("🗑️  Cache cleared")
    return {"status": "Cache cleared"}

@api_router.post("/refresh")
async def trigger_refresh(background_tasks: BackgroundTasks):
    if plex_client.is_scanning:
        return {"message": "Scan déjà en cours", "status": "busy"}
    logger.info(f"🔄 [Worker {os.getpid()}] Déclenchement scan manuel")
    # Scan manuel = force=True
    background_tasks.add_task(plex_client.refresh_library, force=True)
    return {"message": "Scan démarré", "status": "accepted"}

app.include_router(api_router)

# =============================================================================
# 4. ROUTES FRONTEND & IMAGES
# =============================================================================

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    try:
        return templates.TemplateResponse("index.html", {"request": request})
    except Exception:
        return "<h1>PlexHub Ready</h1>"

@app.get("/proxy-image")
async def proxy_image(url: str, thumb: str, token: str):
    if not thumb: return Response(status_code=404)
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
        resp = await http_client.get(full_url)
        if resp.status_code == 200:
            img_content = resp.content
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
# 5. STREAMING
# =============================================================================

@app.get("/playlist/{play_id}.m3u")
async def get_playlist(play_id: str, server: str, path: str, token: str, title: str = "Video", request: Request = None):
    base_url = str(request.base_url).rstrip('/') if request else ""
    stream_url = f"{base_url}/vlc-stream/{play_id}?server={urllib.parse.quote(server)}&path={urllib.parse.quote(path)}&token={token}"
    return Response(content=f"#EXTM3U\n#EXTINF:-1,{title}\n{stream_url}", media_type="application/x-mpegurl")

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
            logger.info(f"▶️ START Stream {play_id}")
            use_fallback = False
            
            try:
                async with http_client.stream("GET", f"{base_plex}/video/:/transcode/universal/start", 
                                              params=params_opti, headers=headers) as r:
                    if r.status_code == 200:
                        async for chunk in r.aiter_bytes(chunk_size=settings.STREAM_CHUNK_SIZE):
                            yield chunk
                    else:
                        logger.warning(f"⚠️ Transcode 720p refusé ({r.status_code}) -> Fallback")
                        use_fallback = True
            except Exception as e:
                logger.error(f"❌ Erreur stream opti: {e}")
                use_fallback = True

            if use_fallback:
                async with http_client.stream("GET", f"{base_plex}/video/:/transcode/universal/start", 
                                              params=params_fallback, headers=headers) as r:
                    if r.status_code == 200:
                        logger.info(f"✅ Stream Direct Play OK")
                        async for chunk in r.aiter_bytes(chunk_size=settings.STREAM_CHUNK_SIZE):
                            yield chunk
                        
        except Exception as e:
            logger.error(f"❌ Erreur Critique Stream {play_id}: {e}")
        finally:
            stream_semaphore.release()
            logger.info(f"⏹️ END Stream {play_id}")

    return StreamingResponse(
        iter_file(), 
        media_type="video/x-matroska",
        headers={"Content-Disposition": f"inline; filename=stream_{play_id}.mkv"}
    )