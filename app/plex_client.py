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
from app.models import MediaDetail, Source, ServerInfo, SeasonDetail, EpisodeDetail

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
            # S'assurer que le dossier existe
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
            data_to_save = {
                "timestamp": time.time(),
                "servers": [s.model_dump() for s in self.connected_servers],
                "movies": [m.model_dump() for m in self.movies_cache.values()]
            }
            with open(self.db_path, "w", encoding="utf-8") as f:
                json.dump(data_to_save, f, ensure_ascii=False, indent=4)
            
            msg = f"💾 Sauvegarde réussie : {self.db_path} ({len(self.movies_cache)} items)"
            logger.info(msg)
            print(msg) # Trace console garantie
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde cache: {e}")

    def _load_cache_from_disk(self):
        if not self.db_path.exists(): 
            msg = f"📂 Aucun cache trouvé à : {self.db_path}"
            logger.info(msg)
            print(msg)
            return

        try:
            size_bytes = self.db_path.stat().st_size
            size_str = f"{size_bytes / (1024 * 1024):.2f} MB"
            
            with open(self.db_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            self.connected_servers = [ServerInfo(**s) for s in data.get("servers", [])]
            
            loaded_movies = {}
            for m_data in data.get("movies", []):
                movie = MediaDetail(**m_data)
                loaded_movies[movie.id] = movie
            
            self.movies_cache = loaded_movies
            self.last_scan_time = data.get("timestamp", 0)
            
            msg = f"📂 Cache chargé : {size_str} | {len(self.movies_cache)} items trouvés sur disque."
            logger.info(msg)
            print(msg) # Trace console garantie
        except Exception as e:
            logger.error(f"❌ Erreur au chargement du cache : {e}")
            print(f"❌ Erreur au chargement du cache : {e}")
            self.movies_cache = {}

    # --- LOGIQUE DE SCAN ---
    async def _connect_and_scan(self, resource):
        start_time = time.time()
        try:
            logger.info(f"🔌 Connexion à {resource.name}...")
            server = await asyncio.to_thread(resource.connect, timeout=60)
            latency = round((time.time() - start_time) * 1000, 2)
            
            self.connected_servers.append(ServerInfo(
                name=resource.name, url=server._baseurl, owned=resource.owned, latency=latency
            ))

            sections = await asyncio.to_thread(server.library.sections)
            
            for section in sections:
                if section.type not in ["movie", "show"]: continue
                
                logger.info(f"   📖 [{resource.name}] Scan Section '{section.title}' ({section.type})...")
                items = await asyncio.to_thread(section.all)
                logger.info(f"   └── {len(items)} éléments trouvés dans '{section.title}' [{resource.name}].")

                for item in items:
                    episodes_data = []
                    
                    # --- RECUPERATION EPISODES ---
                    if section.type == "show":
                        try:
                            # Récupération optimisée
                            all_eps = await asyncio.to_thread(item.episodes)
                            
                            seasons_found = set(ep.seasonNumber for ep in all_eps if ep.seasonNumber is not None)
                            nb_seasons = len(seasons_found)
                            nb_eps = len(all_eps)

                            if nb_eps > 0:
                                logger.info(f"      📺 Série '{item.title}' [{resource.name}] : {nb_seasons} Saison(s) | {nb_eps} Épisodes")
                            else:
                                logger.warning(f"      ⚠️ Série '{item.title}' [{resource.name}] : Aucun épisode trouvé !")

                            for ep in all_eps:
                                episodes_data.append({
                                    "season": ep.seasonNumber,
                                    "index": ep.index,
                                    "title": ep.title,
                                    "summary": ep.summary or "",
                                    "thumb": ep.thumb,
                                    "key": ep.key,
                                    "media": ep.media
                                })
                        except Exception as e:
                            logger.error(f"      ❌ Erreur scan série '{item.title}': {e}")

                    self._process_item(item, section.type, resource, server, episodes_data)
                    
            logger.info(f"✅ [Scan] {resource.name} OK ({latency}ms)")
        except Exception as e:
            logger.warning(f"⚠️ [Scan] Échec {resource.name}: {str(e)}")

    def _process_item(self, item, section_type, resource, server, episodes_data=[]):
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

            # Resolution (Films uniquement)
            resolution = "SD"
            if section_type == "movie" and item.media:
                try:
                    res = str(item.media[0].videoResolution).upper()
                    resolution = res + "P" if res.isdigit() else res
                except: pass

            raw_genres = [g.tag for g in item.genres] if item.genres else []
            normalized_genres = list(set([self._normalize_genre(g) for g in raw_genres]))
            normalized_genres.sort()

            director = "Série TV"
            if section_type == "movie" and item.directors:
                director = item.directors[0].tag

            # --- SÉCURISATION RATING ---
            rating_value = 0.0
            if item.rating is not None:
                try:
                    rating_value = round(float(item.rating), 1)
                except: 
                    rating_value = 0.0

            self.raw_cache[key].append({
                "play_id": str(uuid.uuid4()),
                "type": section_type, 
                "title": item.title,
                "year": item.year or 0,
                "thumb": item.thumb,
                "rating": rating_value,
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
                "episodes": episodes_data
            })
        except Exception as e:
            logger.warning(f"⚠️ Skip item '{item.title}' (Donnée invalide): {e}")

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

    def _build_url_params(self, inst, key=None):
        k = key if key else inst['key']
        return (
            f"server={urllib.parse.quote(inst['server_url'])}&"
            f"path={urllib.parse.quote(k)}&"
            f"token={inst['server_token']}"
        )

    def _build_api_cache(self):
        new_cache = {}
        for key, instances in self.raw_cache.items():
            main = next((i for i in instances if i['is_owned']), instances[0])
            
            poster_link = ""
            if main['thumb']:
                poster_link = f"/proxy-image?url={urllib.parse.quote(main['server_url'])}&thumb={urllib.parse.quote(main['thumb'])}&token={main['server_token']}"

            media_item = MediaDetail(
                id=key,
                type=main['type'],
                title=main['title'],
                year=main['year'],
                director=main['director'],
                genres=main['genres'],
                summary=main['summary'],
                rating=max([i['rating'] for i in instances]),
                poster_url=poster_link,
            )

            # --- FILMS ---
            if main['type'] == 'movie':
                for inst in instances:
                    params = self._build_url_params(inst)
                    media_item.sources.append(Source(
                        server_name=inst['server_name'],
                        resolution=inst['resolution'],
                        is_owned=inst['is_owned'],
                        stream_url=f"/vlc-stream/{inst['play_id']}?{params}",
                        m3u_url=f"/playlist/{inst['play_id']}.m3u?{params}&title={urllib.parse.quote(inst['title'])}",
                        plex_deeplink=f"plex://preplay/?metadataKey={inst['key']}&server={inst['machine_id']}",
                        plex_web_url=f"https://app.plex.tv/desktop/#!/server/{inst['machine_id']}/details?key={urllib.parse.quote(inst['key'])}"
                    ))

            # --- SÉRIES ---
            elif main['type'] == 'show':
                seasons_map = defaultdict(lambda: defaultdict(dict)) 
                
                for inst in instances:
                    for ep in inst['episodes']:
                        # --- SÉCURISATION EPISODES (Index None = 0) ---
                        s_idx = ep['season'] if ep['season'] is not None else 0
                        e_idx = ep['index'] if ep['index'] is not None else 0
                        
                        if not seasons_map[s_idx].get(e_idx):
                            thumb_url = ""
                            if ep['thumb']:
                                thumb_url = f"/proxy-image?url={urllib.parse.quote(inst['server_url'])}&thumb={urllib.parse.quote(ep['thumb'])}&token={inst['server_token']}"
                            
                            seasons_map[s_idx][e_idx] = EpisodeDetail(
                                id=f"S{s_idx:02d}E{e_idx:02d}", 
                                index=e_idx,
                                title=ep['title'],
                                summary=ep['summary'],
                                thumb_url=thumb_url
                            )
                        
                        res = "SD"
                        try:
                            if ep['media']:
                                r = str(ep['media'][0].videoResolution).upper()
                                res = r + "P" if r.isdigit() else r
                        except: pass

                        play_id = str(uuid.uuid4())
                        params = self._build_url_params(inst, key=ep['key'])
                        
                        seasons_map[s_idx][e_idx].sources.append(Source(
                            server_name=inst['server_name'],
                            resolution=res,
                            is_owned=inst['is_owned'],
                            stream_url=f"/vlc-stream/{play_id}?{params}",
                            m3u_url=f"/playlist/{play_id}.m3u?{params}&title={urllib.parse.quote(inst['title'] + ' ' + ep['title'])}",
                            plex_deeplink=f"plex://preplay/?metadataKey={ep['key']}&server={inst['machine_id']}",
                            plex_web_url=f"https://app.plex.tv/desktop/#!/server/{inst['machine_id']}/details?key={urllib.parse.quote(ep['key'])}"
                        ))

                for s_num in sorted(seasons_map.keys()):
                    eps_list = [seasons_map[s_num][e] for e in sorted(seasons_map[s_num].keys())]
                    if eps_list:
                        media_item.seasons.append(SeasonDetail(
                            index=s_num,
                            title=f"Saison {s_num}",
                            episode_count=len(eps_list),
                            episodes=eps_list
                        ))

            new_cache[key] = media_item
        
        self.movies_cache = new_cache

plex_client = PlexClient()