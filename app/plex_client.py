import asyncio
import uuid
import re
import urllib.parse
import logging
import time
import json
from pathlib import Path
from collections import defaultdict
from plexapi.myplex import MyPlexAccount
from app.config import settings
from app.models import MovieDetail, MovieSource, ServerInfo

logger = logging.getLogger("PlexClient")

class PlexClient:
    GENRE_MAPPING = {
        "action": "Action", "aventure": "Adventure", "animation": "Animation",
        "biographie": "Biography", "comédie": "Comedy", "comedie": "Comedy",
        "crime": "Crime", "documentaire": "Documentary", "drame": "Drama",
        "famille": "Family", "fantastique": "Fantasy", "fantasy": "Fantasy",
        "histoire": "History", "horreur": "Horror", "musique": "Music",
        "mystère": "Mystery", "romance": "Romance", "science-fiction": "Sci-Fi",
        "sci-fi": "Sci-Fi", "thriller": "Thriller", "guerre": "War", "western": "Western"
    }

    def __init__(self):
        self.movies_cache = {}          
        self.raw_cache = defaultdict(list)
        self.connected_servers = []
        self.scan_status = "Initialisation"
        self.last_scan_time = 0
        self.is_scanning = False
        self.db_path = settings.CACHE_DIR / "library_cache.json"
        self._load_cache_from_disk()

    def _normalize_genre(self, genre_tag: str) -> str:
        if not genre_tag: return "Unknown"
        clean = genre_tag.strip().lower()
        return self.GENRE_MAPPING.get(clean, genre_tag.title())

    def get_chrome_headers(self, token: str, session_id: str = settings.CLIENT_ID):
        return {
            "X-Plex-Client-Identifier": session_id,
            "X-Plex-Product": "Plex Web",
            "X-Plex-Version": "4.100.1",
            "X-Plex-Platform": "Chrome",
            "X-Plex-Device": "Android TV Backend",
            "X-Plex-Token": token,
            "Accept": "*/*",
            "Accept-Language": "fr"
        }

    # --- PERSISTANCE ---
    def _save_cache_to_disk(self):
        try:
            data_to_save = {
                "timestamp": time.time(),
                "servers": [s.model_dump() for s in self.connected_servers],
                "movies": [m.model_dump() for m in self.movies_cache.values()]
            }
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False)
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde cache: {e}")

    def _load_cache_from_disk(self):
        if not self.db_path.exists(): return
        try:
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.connected_servers = [ServerInfo(**s) for s in data.get("servers", [])]
            loaded_movies = {}
            for m_data in data.get("movies", []):
                movie = MovieDetail(**m_data)
                loaded_movies[movie.id] = movie
            self.movies_cache = loaded_movies
            self.last_scan_time = data.get("timestamp", 0)
            self.scan_status = f"Restauré ({len(self.movies_cache)} items)"
            logger.info(f"🚀 Cache restauré : {len(self.movies_cache)} items.")
        except Exception:
            self.movies_cache = {}

    # --- LOGIQUE DE SCAN ---
    async def _connect_and_scan(self, resource):
        start_time = time.time()
        try:
            server = await asyncio.to_thread(resource.connect, timeout=60)
            latency = round((time.time() - start_time) * 1000, 2)
            
            self.connected_servers.append(ServerInfo(
                name=resource.name, url=server._baseurl, owned=resource.owned, latency=latency
            ))

            sections = await asyncio.to_thread(server.library.sections)
            
            for section in sections:
                # INTEGRATION 1 : On accepte aussi les séries ("show")
                if section.type not in ["movie", "show"]: continue
                
                items = await asyncio.to_thread(section.all)
                
                for item in items:
                    self._process_item(item, section.type, resource, server)
                    
            logger.info(f"✅ [Scan] {resource.name} ({latency}ms) - OK")
        except Exception as e:
            logger.warning(f"⚠️ [Scan] Échec {resource.name}: {str(e)}")

    def _process_item(self, item, section_type, resource, server):
        try:
            # ID Unique
            imdb_id = None
            if item.guids:
                for guid in item.guids:
                    if 'imdb' in guid.id:
                        match = re.search(r'tt\d+', guid.id)
                        if match: imdb_id = match.group(0)
                        break
            key = imdb_id if imdb_id else f"{item.title}-{item.year}"

            # Résolution (Logique adaptée pour Séries)
            resolution = "SD"
            try:
                if section_type == "movie" and item.media:
                    res = str(item.media[0].videoResolution).upper()
                    resolution = res + "P" if res.isdigit() else res
                elif section_type == "show":
                    # Pour une série, on regarde le premier épisode pour estimer la qualité
                    # Note : Ceci est un appel bloquant potentiel, à surveiller en perf
                    # Dans une V2, on pourrait éviter cet appel si trop lent
                    # episodes = item.episodes() 
                    # Pour l'instant on met une valeur par défaut pour ne pas ralentir le scan
                    resolution = "TV" 
            except: pass

            raw_genres = [g.tag for g in item.genres] if item.genres else []
            normalized_genres = list(set([self._normalize_genre(g) for g in raw_genres]))
            normalized_genres.sort()

            # Directeur : "Série TV" pour les shows
            director = "Série TV"
            if section_type == "movie" and item.directors:
                director = item.directors[0].tag

            self.raw_cache[key].append({
                "play_id": str(uuid.uuid4()),
                "type": section_type, # 'movie' ou 'show'
                "title": item.title,
                "year": item.year or 0,
                "thumb": item.thumb,
                "rating": float(f"{item.rating:.1f}") if item.rating else 0.0,
                "summary": item.summary or "",
                "server_name": resource.name,
                "server_url": server._baseurl,
                "server_token": resource.accessToken,
                "machine_id": server.machineIdentifier,
                "key": item.key,
                "is_owned": resource.owned,
                "genres": normalized_genres,
                "director": director,
                "resolution": resolution,
            })
        except Exception: pass

    async def refresh_library(self, force: bool = False):
        if self.is_scanning: return
        now = time.time()
        if not force and (now - self.last_scan_time) < settings.SCAN_CACHE_TTL:
            if self.movies_cache: return

        self.is_scanning = True
        self.scan_status = "Scan Réseau..."
        self.raw_cache = defaultdict(list)
        self.connected_servers = []

        try:
            logger.info("🚀 Démarrage Scan Parallèle...")
            account = await asyncio.to_thread(MyPlexAccount, token=settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            target_resources = [r for r in resources if "server" in r.provides]
            if settings.ONLY_OWNED:
                target_resources = [r for r in target_resources if r.owned]

            await asyncio.gather(*(self._connect_and_scan(res) for res in target_resources))
            self._build_api_cache()
            self.last_scan_time = time.time()
            self.scan_status = "Terminé"
            self._save_cache_to_disk()
            logger.info(f"✨ Scan Terminé: {len(self.movies_cache)} items.")
        except Exception as e:
            self.scan_status = f"Erreur: {e}"
            logger.error(f"❌ Erreur Scan: {e}")
        finally:
            self.is_scanning = False

    def _build_api_cache(self):
        new_cache = {}
        for key, instances in self.raw_cache.items():
            main = next((i for i in instances if i['is_owned']), instances[0])
            
            poster_link = ""
            if main['thumb']:
                poster_link = f"/proxy-image?url={urllib.parse.quote(main['server_url'])}&thumb={urllib.parse.quote(main['thumb'])}&token={main['server_token']}"

            sources_list = []
            best_rating = 0.0
            
            for inst in instances:
                if inst['rating'] > best_rating: best_rating = inst['rating']
                
                # Paramètres communs pour les URLs
                params = (
                    f"server={urllib.parse.quote(inst['server_url'])}&"
                    f"path={urllib.parse.quote(inst['key'])}&"
                    f"token={inst['server_token']}"
                )

                stream_link = f"/vlc-stream/{inst['play_id']}?{params}"
                
                # INTEGRATION 2 : Génération de l'URL Playlist M3U
                # On ajoute le titre pour le #EXTINF
                m3u_link = f"/playlist/{inst['play_id']}.m3u?{params}&title={urllib.parse.quote(inst['title'])}"

                deeplink = f"plex://preplay/?metadataKey={inst['key']}&server={inst['machine_id']}"
                web_link = f"https://app.plex.tv/desktop/#!/server/{inst['machine_id']}/details?key={urllib.parse.quote(inst['key'])}"
                
                sources_list.append(MovieSource(
                    server_name=inst['server_name'],
                    resolution=inst['resolution'],
                    is_owned=inst['is_owned'],
                    stream_url=stream_link,
                    m3u_url=m3u_link, # <--- Ajouté ici
                    plex_deeplink=deeplink,
                    plex_web_url=web_link
                ))

            new_cache[key] = MovieDetail(
                id=key,
                type=main['type'], # <--- 'movie' ou 'show'
                title=main['title'],
                year=main['year'],
                director=main['director'],
                genres=main['genres'],
                summary=main['summary'],
                rating=best_rating,
                poster_url=poster_link,
                sources=sources_list
            )
        self.movies_cache = new_cache

plex_client = PlexClient()