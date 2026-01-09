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
        if not self.db_path.exists(): 
            logger.info("📂 Aucun cache sur le disque. Démarrage à vide.")
            return

        try:
            # Calcul de la taille du fichier
            size_bytes = self.db_path.stat().st_size
            size_str = f"{size_bytes / 1024:.2f} KB"
            if size_bytes > 1024 * 1024:
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
            
            count = len(self.movies_cache)
            self.scan_status = f"Restauré ({count} items)"
            logger.info(f"📂 Cache chargé depuis le disque : {size_str} | {count} médias récupérés.")
        except Exception as e:
            logger.error(f"❌ Cache corrompu ou illisible : {e}")
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
            total_items_server = 0
            
            for section in sections:
                if section.type not in ["movie", "show"]: continue
                
                # LOG DÉTAILLÉ : On indique quelle librairie on scanne
                logger.info(f"   📖 Scan Section '{section.title}' ({section.type}) sur {resource.name}...")
                
                items = await asyncio.to_thread(section.all)
                count_section = len(items)
                total_items_server += count_section
                
                # LOG TAILLE : Nombre d'éléments trouvés dans cette section
                logger.info(f"   └── {count_section} éléments trouvés dans '{section.title}'")

                for item in items:
                    # (Logique épisodes inchangée...)
                    episodes_data = []
                    if section.type == "show":
                        try:
                            all_eps = await asyncio.to_thread(item.episodes)
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
                        except: pass

                    self._process_item(item, section.type, resource, server, episodes_data)
                    
            logger.info(f"✅ [Scan] {resource.name} Terminé en {latency}ms - Total: {total_items_server} médias ajoutés.")
        except Exception as e:
            logger.warning(f"⚠️ [Scan] Échec {resource.name}: {str(e)}")

    def _process_item(self, item, section_type, resource, server, episodes_data=[]):
        try:
            # ID Unique (IMDb ou Titre-Année)
            imdb_id = None
            if item.guids:
                for guid in item.guids:
                    if 'imdb' in guid.id:
                        match = re.search(r'tt\d+', guid.id)
                        if match: imdb_id = match.group(0)
                        break
            key = imdb_id if imdb_id else f"{item.title}-{item.year}"

            # Extraction Resolution (Pour Films)
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

            # Construction de l'objet brut
            entry = {
                "play_id": str(uuid.uuid4()),
                "type": section_type, 
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
                "episodes": episodes_data # Liste des épisodes bruts pour cette instance
            }
            
            self.raw_cache[key].append(entry)
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
            # Instance principale (Priorité au propriétaire)
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
                rating=max([i['rating'] for i in instances]), # Meilleure note trouvée
                poster_url=poster_link,
            )

            # --- LOGIQUE FILMS ---
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

            # --- LOGIQUE SÉRIES (Agrégation Complexe) ---
            elif main['type'] == 'show':
                # On utilise un dictionnaire temporaire pour fusionner les épisodes de tous les serveurs
                # Structure : seasons[s_num][e_num] = EpisodeDetail
                seasons_map = defaultdict(lambda: defaultdict(dict)) 
                
                for inst in instances:
                    for ep in inst['episodes']:
                        s_idx = ep['season']
                        e_idx = ep['index']
                        
                        # Si l'épisode n'existe pas encore dans notre carte, on le crée
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
                        
                        # Calcul Résolution Épisode
                        res = "SD"
                        try:
                            if ep['media']:
                                r = str(ep['media'][0].videoResolution).upper()
                                res = r + "P" if r.isdigit() else r
                        except: pass

                        # Ajout de la source à l'épisode existant
                        play_id = str(uuid.uuid4()) # Nouvel ID pour ce flux spécifique
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

                # Conversion du Map en Liste triée
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