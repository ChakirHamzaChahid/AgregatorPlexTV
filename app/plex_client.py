import asyncio
import uuid
import re
import urllib.parse
import logging
import time
import sqlite3
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
        self.is_scanning = False
        self.scan_status = "Initialisation"
        self.raw_cache = defaultdict(list)
        self.db_path = settings.CACHE_DIR / "library.db"
        self._init_db()

    def _init_db(self):
        """Initialisation robuste de la base SQLite."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
           # timeout=20 laisse le temps au premier worker de finir l'init
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL") # Performance SSD NVMe
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS media (
                        id TEXT PRIMARY KEY, type TEXT, data TEXT, timestamp REAL
                    )
                """)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS servers (
                        name TEXT PRIMARY KEY, data TEXT
                    )
                """)
               
                # Un seul log pour confirmer
            if not hasattr(self, '_db_init_done'):
                logger.info(f"📂 SQLite : {self.db_path.name} prête.")
                self._db_init_done = True
        except Exception as e:
            logger.error(f"❌ Erreur Init SQLite: {e}")

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

    # --- PERSISTANCE SQLITE (Remplace JSON) ---
    def _save_to_db(self, media_dict, servers_list):
        try:
            with sqlite3.connect(self.db_path) as conn:
                # Mise à jour des serveurs
                conn.execute("DELETE FROM servers")
                for s in servers_list:
                    conn.execute("INSERT INTO servers (name, data) VALUES (?, ?)",
                                (s.name, s.model_dump_json()))
                
                # Mise à jour des médias
                ts = time.time()
                for m_id, m_obj in media_dict.items():
                    conn.execute("INSERT OR REPLACE INTO media (id, type, data, timestamp) VALUES (?, ?, ?, ?)",
                                (m_id, m_obj.type, m_obj.model_dump_json(), ts))
            
            msg = f"💾 Sauvegarde SQLite réussie : {len(media_dict)} items synchronisés."
            logger.info(msg)
            print(msg)
        except Exception as e:
            logger.error(f"❌ Erreur sauvegarde SQLite: {e}")

    def get_all_media(self):
        """Lecture depuis SQLite pour main.py (Economie RAM)."""
        results = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT data FROM media")
                for row in cursor:
                    m_data = json.loads(row[0])
                    results[m_data['id']] = MediaDetail(**m_data)
        except Exception as e:
            logger.error(f"❌ Erreur lecture media SQLite: {e}")
        return results

    def get_connected_servers(self):
        """Récupération des serveurs pour l'API."""
        servers = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT data FROM servers")
                for row in cursor:
                    servers.append(ServerInfo(**json.loads(row[0])))
        except: pass
        return servers

    # --- LOGIQUE DE SCAN ---
    async def refresh_library(self, force: bool = False):
        if self.is_scanning: return
        if not settings.PLEX_TOKEN:
            logger.error("❌ Scan annulé : PLEX_TOKEN est vide. Vérifiez votre fichier .env")
            return
        self.is_scanning = True
        self.scan_status = "Scan Réseau..."
        self.raw_cache = defaultdict(list)
        connected_servers_temp = []

        try:
            logger.info("🚀 Démarrage Scan Parallèle (Mode SQLite)...")
            account = await asyncio.to_thread(MyPlexAccount, token=settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            target_resources = [r for r in resources if "server" in r.provides]
            
            if settings.ONLY_OWNED:
                target_resources = [r for r in target_resources if r.owned]

            await asyncio.gather(*(self._connect_and_scan(res, connected_servers_temp) for res in target_resources))
            
            new_cache = self._build_api_cache()
            self._save_to_db(new_cache, connected_servers_temp)
            
            self.scan_status = "Terminé"
            logger.info(f"✨ Scan Terminé: {len(new_cache)} items en base.")
        except Exception as e:
            self.scan_status = f"Erreur: {e}"
            logger.error(f"❌ Erreur Scan: {e}")
        finally:
            self.is_scanning = False

    async def _connect_and_scan(self, resource, servers_list):
        start_time = time.time()
        try:
            logger.info(f"🔌 Connexion à {resource.name}...")
            server = await asyncio.to_thread(resource.connect, timeout=60)
            latency = round((time.time() - start_time) * 1000, 2)
            
            servers_list.append(ServerInfo(
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
                    if section.type == "show":
                        try:
                            all_eps = await asyncio.to_thread(item.episodes)
                            if len(all_eps) > 0:
                                logger.info(f"      📺 Série '{item.title}' [{resource.name}] : {len(all_eps)} Épisodes")
                            
                            for ep in all_eps:
                                episodes_data.append({
                                    "season": ep.seasonNumber, "index": ep.index,
                                    "title": ep.title, "summary": ep.summary or "",
                                    "thumb": ep.thumb, "key": ep.key, "media": ep.media
                                })
                        except Exception as e:
                            logger.error(f"      ❌ Erreur scan série '{item.title}': {e}")

                    self._process_item(item, section.type, resource, server, episodes_data)
            
            logger.info(f"✅ [Scan] {resource.name} OK ({latency}ms)")
        except Exception as e:
            logger.warning(f"⚠️ [Scan] Échec {resource.name}: {str(e)}")

    def _process_item(self, item, section_type, resource, server, episodes_data=[]):
        try:
            imdb_id = None
            if item.guids:
                for guid in item.guids:
                    if 'imdb' in guid.id:
                        match = re.search(r'tt\d+', guid.id)
                        if match: imdb_id = match.group(0)
                        break
            key = imdb_id if imdb_id else f"{item.title}-{item.year}"

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

            rating_value = 0.0
            if item.rating is not None:
                try: rating_value = round(float(item.rating), 1)
                except: rating_value = 0.0

            self.raw_cache[key].append({
                "play_id": str(uuid.uuid4()), "type": section_type, "title": item.title,
                "year": item.year or 0, "thumb": item.thumb, "rating": rating_value,
                "summary": item.summary or "", "server_name": resource.name,
                "server_url": server._baseurl, "server_token": resource.accessToken,
                "machine_id": server.machineIdentifier, "key": item.key,
                "is_owned": resource.owned, "genres": normalized_genres,
                "director": director, "resolution": resolution, "episodes": episodes_data
            })
        except Exception as e:
            logger.warning(f"⚠️ Skip item '{item.title}' (Donnée invalide): {e}")

    def _build_url_params(self, inst, key=None):
        k = key if key else inst['key']
        return f"server={urllib.parse.quote(inst['server_url'])}&path={urllib.parse.quote(k)}&token={inst['server_token']}"

    def _build_api_cache(self):
        new_cache = {}
        for key, instances in self.raw_cache.items():
            main = next((i for i in instances if i['is_owned']), instances[0])
            
            poster_link = ""
            if main['thumb']:
                poster_link = f"/proxy-image?url={urllib.parse.quote(main['server_url'])}&thumb={urllib.parse.quote(main['thumb'])}&token={main['server_token']}"

            media_item = MediaDetail(
                id=key, type=main['type'], title=main['title'], year=main['year'],
                director=main['director'], genres=main['genres'], summary=main['summary'],
                rating=max([i['rating'] for i in instances]), poster_url=poster_link
            )

            if main['type'] == 'movie':
                for inst in instances:
                    params = self._build_url_params(inst)
                    media_item.sources.append(Source(
                        server_name=inst['server_name'], resolution=inst['resolution'],
                        is_owned=inst['is_owned'], stream_url=f"/vlc-stream/{inst['play_id']}?{params}",
                        m3u_url=f"/playlist/{inst['play_id']}.m3u?{params}&title={urllib.parse.quote(inst['title'])}",
                        plex_deeplink=f"plex://preplay/?metadataKey={inst['key']}&server={inst['machine_id']}",
                        plex_web_url=f"https://app.plex.tv/desktop/#!/server/{inst['machine_id']}/details?key={urllib.parse.quote(inst['key'])}"
                    ))

            elif main['type'] == 'show':
                seasons_map = defaultdict(lambda: defaultdict(dict)) 
                for inst in instances:
                    for ep in inst['episodes']:
                        s_idx = ep['season'] if ep['season'] is not None else 0
                        e_idx = ep['index'] if ep['index'] is not None else 0
                        
                        if not seasons_map[s_idx].get(e_idx):
                            thumb_url = ""
                            if ep['thumb']:
                                thumb_url = f"/proxy-image?url={urllib.parse.quote(inst['server_url'])}&thumb={urllib.parse.quote(ep['thumb'])}&token={inst['server_token']}"
                            
                            seasons_map[s_idx][e_idx] = EpisodeDetail(
                                id=f"S{s_idx:02d}E{e_idx:02d}", index=e_idx, title=ep['title'],
                                summary=ep['summary'], thumb_url=thumb_url
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
                            server_name=inst['server_name'], resolution=res, is_owned=inst['is_owned'],
                            stream_url=f"/vlc-stream/{play_id}?{params}",
                            m3u_url=f"/playlist/{play_id}.m3u?{params}&title={urllib.parse.quote(inst['title'] + ' ' + ep['title'])}",
                            plex_deeplink=f"plex://preplay/?metadataKey={ep['key']}&server={inst['machine_id']}",
                            plex_web_url=f"https://app.plex.tv/desktop/#!/server/{inst['machine_id']}/details?key={urllib.parse.quote(ep['key'])}"
                        ))

                for s_num in sorted(seasons_map.keys()):
                    eps_list = [seasons_map[s_num][e] for e in sorted(seasons_map[s_num].keys())]
                    if eps_list:
                        media_item.seasons.append(SeasonDetail(
                            index=s_num, title=f"Saison {s_num}",
                            episode_count=len(eps_list), episodes=eps_list
                        ))

            new_cache[key] = media_item
        return new_cache

plex_client = PlexClient()