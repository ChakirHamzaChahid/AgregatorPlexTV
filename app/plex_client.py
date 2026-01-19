import asyncio
import uuid
import re
import urllib.parse
import logging
import time
import sqlite3
import json
import os
import unicodedata
from pathlib import Path
from collections import defaultdict

# --- IMPORT CRITIQUE ---
import plexapi
from plexapi.myplex import MyPlexAccount
# -----------------------

from app.config import settings
from app.models import MediaDetail, Source, ServerInfo, SeasonDetail, EpisodeDetail, AudioTrack, Subtitle, Chapter, Collection, Marker, SimilarItem
from app.plex_extensions import PlexExtensions

logger = logging.getLogger("PlexClient")

# =============================================================================
# CORRECTION 1 : IDENTITÉ FIGÉE (Arrête les notifs "New Device")
# =============================================================================
plexapi.X_PLEX_CLIENT_IDENTIFIER = settings.CLIENT_ID
plexapi.X_PLEX_PRODUCT = "PlexHub Backend"
plexapi.X_PLEX_DEVICE = "PlexHub Server"
plexapi.X_PLEX_VERSION = "1.0.0"
plexapi.X_PLEX_PLATFORM = "Linux"

class PlexClient(PlexExtensions):
    """
    Client principal gérant l'interaction avec l'écosystème Plex.
    
    Responsabilités :
    1. Authentification et découverte des serveurs via Plex.tv.
    2. Agrégation des bibliothèques de multiples serveurs (Own & Shared).
    3. Mise en cache locale (SQLite) des métadonnées pour la performance.
    4. Construction d'une vue unifiée (Média UNIQUE avec SOURCES multiples).
    """
    GENRE_MAPPING = {
        # Standardisation des genres (Français/Anglais -> Français unifié)
        "action": "Action", "aventure": "Adventure", "animation": "Animation",
        "biographie": "Biography", "comédie": "Comedy", "comedie": "Comedy",
        "crime": "Crime", "documentaire": "Documentary", "drame": "Drama",
        "famille": "Family", "fantastique": "Fantasy", "fantasy": "Fantasy",
        "histoire": "History", "horreur": "Horror", "musique": "Music",
        "mystère": "Mystery", "romance": "Romance", "science-fiction": "Sci-Fi",
        "sci-fi": "Sci-Fi", "thriller": "Thriller", "guerre": "War", "western": "Western"
    }

    @staticmethod
    def _normalize_title(title: str) -> str:
        """
        Normalise un titre pour la déduplication robuste.
        - Minuscules
        - Supprime les accents
        - Supprime caractères spéciaux
        - Trim whitespace
        """
        if not title:
            return ""
        
        # Minuscules et trim
        title = title.lower().strip()
        
        # Supprimer accents (é→e, ç→c, etc.)
        title = ''.join(
            c for c in unicodedata.normalize('NFD', title)
            if unicodedata.category(c) != 'Mn'
        )
        
        # Supprimer caractères spéciaux, garder alphanumérique + espaces
        title = ''.join(c if c.isalnum() or c == ' ' else '' for c in title)
        
        # Supprimer espaces multiples
        title = ' '.join(title.split())
        
        return title

    def _get_unique_key(self, item) -> tuple[str, str]:
        """
        Extrait une clé unique pour déduplication avec fallback progressif.
        
        Priority 1: IMDB ID (tt1234567)
        Priority 2: TMDB ID (tmdb-12345)
        Priority 3: Titre normalisé + Année
        
        Returns:
            (key, source_type) 
            ex: ("tt1375666", "imdb") ou ("tmdb-87654", "tmdb") ou ("inception-2010", "title-year")
        """
        # Priority 1: IMDB ID
        if hasattr(item, 'guids') and item.guids:
            for guid in item.guids:
                if 'imdb' in guid.id:
                    match = re.search(r'tt\d+', guid.id)
                    if match:
                        imdb_id = match.group(0)
                        logger.debug(f"   ✅ [IMDB] {item.title} → {imdb_id}")
                        return (imdb_id, "imdb")
        
        # Priority 2: TMDB ID (fallback secondaire)
        if hasattr(item, 'guids') and item.guids:
            for guid in item.guids:
                if 'tmdb' in guid.id:
                    match = re.search(r'\d+', guid.id)
                    if match:
                        tmdb_id = f"tmdb-{match.group(0)}"
                        logger.debug(f"   🎬 [TMDB] {item.title} → {tmdb_id}")
                        if hasattr(item, 'guids'):
                            guids_info = ", ".join([g.id for g in item.guids])
                            logger.debug(f"      GUIDs: {guids_info}")
                        return (tmdb_id, "tmdb")
        
        # Priority 3: Titre normalisé + Année (fallback final)
        title_normalized = self._normalize_title(item.title)
        year = item.year if item.year else "unknown"
        key = f"{title_normalized}-{year}"
        
        logger.warning(f"   ⚠️  [FALLBACK] {item.title} → {key}")
        if hasattr(item, 'guids') and item.guids:
            guids_info = ", ".join([g.id for g in item.guids])
            logger.debug(f"      Available GUIDs: {guids_info}")
        
        return (key, "title-year")

    def __init__(self):
        self.is_scanning = False
        self.scan_status = "Initialisation"
        self.raw_cache = defaultdict(list)
        self.db_path = settings.CACHE_DIR / "library.db"
        self.last_scan_time = 0
        self.settings = settings  # Pour accès dans extensions
        self._init_db()

    def _init_db(self):
        """Initialisation robuste de la base SQLite."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self.db_path, timeout=30) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL") 
                
                # Table principale
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS media_v2 (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        year INTEGER,
                        added_at TEXT, 
                        rating REAL,
                        type TEXT,
                        data TEXT
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_added ON media_v2(added_at)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_title ON media_v2(title)")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON media_v2(type)")
                
                # Table serveurs
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS servers (
                        name TEXT PRIMARY KEY, data TEXT
                    )
                """)
                
                # Table méta (pour le Cooldown Anti-Spam)
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS metadata (
                        key TEXT PRIMARY KEY, value TEXT
                    )
                """)
            
            # Récupération de la dernière date de scan
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT value FROM metadata WHERE key='last_scan'")
                row = cursor.fetchone()
                if row:
                    self.last_scan_time = float(row[0])

            if not hasattr(self, '_db_init_done'):
                logger.info(f"📂 SQLite Optimisée : {self.db_path.name} prête.")
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
            "X-Plex-Product": "PlexHub Web",
            "X-Plex-Version": "4.100.1",
            "X-Plex-Platform": "Chrome",
            "X-Plex-Device": "Android TV Backend",
            "X-Plex-Token": token,
            "Accept": "*/*",
            "Accept-Language": "fr"
        }

    # =========================================================================
    #  PERSISTANCE MODULAIRE (Refactoring Clean Code)
    # =========================================================================

    def _save_servers_tx(self, conn, servers_list):
        conn.execute("DELETE FROM servers")
        for s in servers_list:
            conn.execute("INSERT INTO servers (name, data) VALUES (?, ?)",
                         (s.name, s.model_dump_json()))

    def _prepare_upsert_batch(self, media_dict):
        upsert_data = []
        for m_obj in media_dict.values():
            date_str = m_obj.added_at.isoformat() if m_obj.added_at else "1970-01-01"
            upsert_data.append((
                m_obj.id, m_obj.title, m_obj.year, date_str,
                m_obj.rating, m_obj.type, m_obj.model_dump_json()
            ))
        return upsert_data

    def _perform_upsert_tx(self, conn, upsert_data):
        query_upsert = """
            INSERT INTO media_v2 (id, title, year, added_at, rating, type, data)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title, year = excluded.year, added_at = excluded.added_at,
                rating = excluded.rating, type = excluded.type, data = excluded.data
        """
        conn.executemany(query_upsert, upsert_data)

    def _perform_cleanup_tx(self, conn, current_scanned_ids):
        """
        Nettoyage transactionnel : Supprime de la DB les médias qui ne sont plus présents
        dans aucun des serveurs scannés (gestion des suppressions).
        """
        cursor = conn.execute("SELECT id FROM media_v2")
        existing_ids = {row[0] for row in cursor}
        ids_to_delete = list(existing_ids - set(current_scanned_ids)) # Différence d'ensembles
        if ids_to_delete:
            logger.info(f"🧹 Nettoyage : Suppression de {len(ids_to_delete)} items obsolètes.")
            batch_size = 900 # Limite SQLite pour 'IN (?...)'
            for i in range(0, len(ids_to_delete), batch_size):
                batch = ids_to_delete[i:i + batch_size]
                placeholders = ','.join(['?'] * len(batch))
                conn.execute(f"DELETE FROM media_v2 WHERE id IN ({placeholders})", batch)

    def _save_to_db(self, media_dict, servers_list):
        """Fonction Orchestrateur : Sauvegarde + Mise à jour Date Scan"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                self._save_servers_tx(conn, servers_list)
                upsert_data = self._prepare_upsert_batch(media_dict)
                self._perform_upsert_tx(conn, upsert_data)
                self._perform_cleanup_tx(conn, media_dict.keys())
                
                # MISE À JOUR DATE DERNIER SCAN (Anti-Spam)
                self.last_scan_time = time.time()
                conn.execute("INSERT OR REPLACE INTO metadata (key, value) VALUES ('last_scan', ?)", (str(self.last_scan_time),))
                
                logger.info(f"💾 Sync SQLite Terminée : {len(upsert_data)} items traités.")
        except Exception as e:
            logger.error(f"❌ Erreur critique sauvegarde SQLite: {e}")
            import traceback
            traceback.print_exc()

    # =========================================================================
    #  LECTURE & SCAN
    # =========================================================================

    def get_all_media(self):
        results = {}
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT data FROM media_v2")
                for row in cursor:
                    try:
                        m_data = json.loads(row[0])
                        results[m_data['id']] = MediaDetail(**m_data)
                    except: pass
        except Exception: pass 
        return results
    
    async def get_collections(self):
        """Récupère toutes les collections de tous les serveurs."""
        all_collections = []
        if not settings.PLEX_TOKEN: return []
        
        try:
            account = await asyncio.to_thread(MyPlexAccount, token=settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            target_resources = [r for r in resources if "server" in r.provides]
            if settings.ONLY_OWNED: target_resources = [r for r in target_resources if r.owned]
            
            async def fetch_srv_col(res):
                cols = []
                try:
                    srv = await asyncio.to_thread(res.connect, timeout=10)
                    sections = await asyncio.to_thread(srv.library.sections)
                    for section in sections:
                        if section.type != 'movie': continue # Collections principalement films
                        
                        s_cols = await asyncio.to_thread(section.collections)
                        for c in s_cols:
                            t_url = f"/proxy-image?url={urllib.parse.quote(srv._baseurl)}&thumb={urllib.parse.quote(c.thumb)}&token={res.accessToken}&width=400" if c.thumb else None
                            cols.append(Collection(
                                title=c.title, key=c.ratingKey, 
                                thumb_url=t_url, child_count=c.childCount
                            ))
                except Exception as e:
                    logger.warning(f"⚠️ Erreur Collections {res.name}: {e}")
                return cols

            results = await asyncio.gather(*(fetch_srv_col(r) for r in target_resources))
            for res_list in results:
                all_collections.extend(res_list)
                
        except Exception as e:
            logger.error(f"❌ Erreur Get Collections: {e}")
            
        return all_collections

    async def get_on_deck(self):
        """
        Récupère les éléments 'Continue Watching' (On Deck) de TOUS les serveurs.
        Retourne des objets MediaDetail complets.
        """
        if not settings.PLEX_TOKEN: return []
        on_deck_items = []
        
        try:
            account = await asyncio.to_thread(MyPlexAccount, token=settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            target_resources = [r for r in resources if "server" in r.provides]
            if settings.ONLY_OWNED: target_resources = [r for r in target_resources if r.owned]
            
            for resource in target_resources:
                try:
                    server = await asyncio.to_thread(resource.connect, timeout=10)
                    items = await asyncio.to_thread(server.library.onDeck)
                    
                    for item in items:
                        # Utilisation de la méthode helper de PlexExtensions
                        # On détermine le type 'movie' ou 'show' (souvent absent sur onDeck item mix)
                        m_type = item.type if hasattr(item, 'type') else 'movie'
                        
                        media_detail = await self._item_to_media_detail(
                            item, m_type, resource, server
                        )

                        # --- ENRICHISSEMENT VIA CACHE ---
                        # On remplace l'objet partiel par l'objet complet du cache si dispo
                        try:
                            key = None
                            cached = None
                            
                            if m_type == 'movie':
                                key, _ = self._get_unique_key(item)
                                if key:
                                    cached = self._enrich_media_with_cache(key, None)
                                    
                            elif m_type == 'episode':
                                # Pour un épisode, on cherche la SÉRIE parente pour récupérer
                                # genres, studo, cast, rating du show, backdrop, etc.
                                show_title = getattr(item, 'grandparentTitle', None)
                                if show_title:
                                    # Recherche "Best Effort" par titre de série (Exact Match)
                                    # Car on n'a pas facilement l'ID IMDB de la série depuis l'épisode
                                    with sqlite3.connect(self.db_path) as conn:
                                        cursor = conn.execute(
                                            "SELECT data FROM media_v2 WHERE title = ? AND type = 'show' LIMIT 1",
                                            (show_title,)
                                        )
                                        row = cursor.fetchone()
                                        if row:
                                            show_data = json.loads(row[0])
                                            cached_show = MediaDetail(**show_data)
                                            
                                            # On enrichit l'épisode avec les datas du Show
                                            media_detail.genres = cached_show.genres
                                            media_detail.studio = cached_show.studio
                                            # media_detail.content_rating = cached_show.content_rating # Garder celui de l'ep ou show ?
                                            if not media_detail.backdrop_url and cached_show.backdrop_url:
                                                media_detail.backdrop_url = cached_show.backdrop_url
                                                
                                            # On pourrait aussi préfixer le titre ? "Show - Episode"
                                            # media_detail.title = f"{show_title} - {media_detail.title}"
                                            
                                            logger.debug(f"   ✨ [OnDeck] Episode enrichi via Show: {show_title}")

                            if cached and m_type == 'movie':
                                # On fusionne l'état Live (plus frais) sur l'objet Cache (plus riche)
                                cached.view_offset = media_detail.view_offset
                                cached.view_count = media_detail.view_count
                                cached.last_viewed_at = media_detail.last_viewed_at
                                cached.id = media_detail.id # Garder l'ID extrait initialement (souvent ratingKey ou imdb)
                                
                                media_detail = cached
                                logger.debug(f"   ✨ [OnDeck] Film enrichi via cache: {media_detail.title}")

                        except Exception as e:
                            logger.warning(f"   ⚠️ [OnDeck] Erreur enrichissement {media_detail.title}: {e}")

                        on_deck_items.append(media_detail)
                        
                except Exception as e:
                    logger.warning(f"⚠️ Erreur On Deck {resource.name}: {e}")

        except Exception as e:
            logger.error(f"❌ Erreur Global On Deck: {e}")
            
        return on_deck_items

    async def action_scrobble(self, key: str, action: str):
        """Mark watched/unwatched."""
        try:
            # Note: Pour agir, il faut retrouver l'objet sur le bon serveur
            # Simplification: On cherche sur le premier serveur connecté qui a cet item
            # Dans une version avancée, faudrait stocker quel serveur a quel itemId
            account = await asyncio.to_thread(MyPlexAccount, token=settings.PLEX_TOKEN)
            resource = await asyncio.to_thread(account.resource, settings.SERVER_NAME)
            server = await asyncio.to_thread(resource.connect)
            
            item = await asyncio.to_thread(server.fetchItem, key)
            if action == 'watched':
                await asyncio.to_thread(item.markWatched)
            elif action == 'unwatched':
                await asyncio.to_thread(item.markUnwatched)
            return True
        except Exception as e:
            logger.error(f"❌ Erreur Scrobble {key}: {e}")
            return False

    async def action_progress(self, key: str, time_ms: int):
        """Update progress."""
        try:
            account = await asyncio.to_thread(MyPlexAccount, token=settings.PLEX_TOKEN)
            resource = await asyncio.to_thread(account.resource, settings.SERVER_NAME)
            server = await asyncio.to_thread(resource.connect)
            
            item = await asyncio.to_thread(server.fetchItem, key)
            await asyncio.to_thread(item.updateProgress, time_ms)
            return True
        except Exception as e:
            logger.error(f"❌ Erreur Progress {key}: {e}")
            return False

    def get_connected_servers(self):
        servers = []
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute("SELECT data FROM servers")
                for row in cursor:
                    servers.append(ServerInfo(**json.loads(row[0])))
        except: pass
        return servers

    # --- LOGIQUE DE SCAN ---
    # --- LOGIQUE DE SCAN ---
    async def refresh_library(self, force: bool = False):
        """
        Lance le scan complet de tous les serveurs Plex connectés.
        
        Étapes :
        1. Authentification MyPlex.
        2. Récupération liste serveurs (Resource Discovery).
        3. Scan PARALLÈLE de chaque serveur (Asyncio Gather).
        4. Déduplication et Mérging des résultats (plusieurs sources pour un même film).
        5. Sauvegarde atomique en base de données.
        """
        if self.is_scanning: return
        if not settings.PLEX_TOKEN:
            logger.error("❌ Scan annulé : PLEX_TOKEN vide.")
            return
        
        # =====================================================================
        # CORRECTION 2 : ANTI-SPAM (COOLDOWN 1 HEURE)
        # =====================================================================
        if not force:
            time_since_last = time.time() - self.last_scan_time
            if time_since_last < 3600: # 1 heure
                logger.info(f"⏳ Scan ignoré (Dernier scan il y a {int(time_since_last/60)} min).")
                return
        
        self.is_scanning = True
        self.scan_status = "Scan Réseau..."
        self.raw_cache = defaultdict(list)
        connected_servers_temp = []

        try:
            logger.info("🚀 Démarrage Scan Parallèle (Mode SQLite)...")
            # Appel API MyPlex pour lister les ressources (serveurs)
            account = await asyncio.to_thread(MyPlexAccount, token=settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            target_resources = [r for r in resources if "server" in r.provides]
            
            if settings.ONLY_OWNED:
                target_resources = [r for r in target_resources if r.owned]

            # Exécution concurrente des scans de serveurs
            await asyncio.gather(*(self._connect_and_scan(res, connected_servers_temp) for res in target_resources))
            
            # Construction du cache API final (Mérging)
            new_cache = self._build_api_cache()
            
            # Persistance
            self._save_to_db(new_cache, connected_servers_temp)
            
            self.scan_status = "Terminé"
            logger.info(f"✨ Scan Terminé: {len(new_cache)} items en base.")
            
        except Exception as e:
            self.scan_status = f"Erreur: {e}"
            logger.error(f"❌ Erreur Scan Global: {e}")
        finally:
            self.is_scanning = False

    async def _connect_and_scan(self, resource, servers_list):
        start_time = time.time()
        try:
            logger.info(f"🔌 Connexion à {resource.name}...")
            server = await asyncio.to_thread(resource.connect, timeout=60)
            latency = round((time.time() - start_time) * 1000, 2)
            
            # Feature 11: Infos Serveur Détaillées
            servers_list.append(ServerInfo(
                name=resource.name,
                url=server._baseurl,
                owned=resource.owned,
                latency=latency,
                version=server.version,
                plex_pass=server.myPlexSubscription,
                transcoder_available=server.transcoderVideo,
                active_activities=[a.type for a in server.activities] if server.activities else []
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
                            # Optimisation: On ne charge les épisodes que si la liste est vide
                            # pour éviter les appels réseaux inutiles si on a déjà des infos
                            # (Ajuster selon besoin de précision vs vitesse)
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
                            logger.error(f"❌ Erreur scan série '{item.title}': {e}")


                    self._process_item(item, section.type, resource, server, episodes_data)
            
            logger.info(f"✅ [Scan] {resource.name} OK ({latency}ms)")
        except Exception as e:
            logger.warning(f"⚠️ [Scan] Échec {resource.name}: {str(e)}")

    def _process_item(self, item, section_type, resource, server, episodes_data=[]):
        """
        Normalise un élément brut Plex (Film/Série) en une structure intermédiaire.
        Gère la détection IMDB pour la clé unique de fusion avec fallbacks progressifs.
        """
        try:
            # --- 1. Extraction de la clé unique (IMDB > TMDB > Titre-Année) ---
            key, key_source = self._get_unique_key(item)

            # Extraction Labels (Feature 10)
            labels = [l.tag for l in item.labels] if hasattr(item, 'labels') else []

            # Extraction Trailers (Feature 9)
            trailers_list = []
            if hasattr(item, 'extras'):
                 # Note: item.extras peut faire un appel réseau, attention à la perf
                 # On suppose que lors d'un scan complet 'item' a déjà ces infos ou que c'est acceptable
                 # Pour optimiser, on pourrait le faire en lazy loading, mais pour le cache on le veut direct
                 try:
                     # On ne peut pas appeler item.extras() en async ici facilement si c'est une méthode bloquante
                     # Mais plexapi est synchrone (wrappé dans asyncio.to_thread pour les appels parents)
                     # Ici on est DANS un thread pool via _process_item appelé par refresh_library ? 
                     # Non refresh_library appelle _connect_and_scan -> _process_item
                     # Et _process_item est synchrone. Donc on peut utiliser les méthodes synchrones de l'objet item.
                     pass 
                     # MAIS: item.extras force souvent un reload. 
                     # On va tenter d'accéder à la propriété si chargée, sinon skip pour perf scan global
                     # Si 'extras' n'est pas préchargé, ça va ralentir le scan énormément
                 except: pass

            imdb_rating = None
            rotten_rating = None
            if hasattr(item, 'ratings') and item.ratings:
                for r in item.ratings:
                    img = getattr(r, 'image', '').lower()
                    if 'imdb' in img: 
                        try: imdb_rating = float(r.value)
                        except: pass
                    elif 'tomato' in img: 
                        try: rotten_rating = int(float(r.value) * 100) if r.value <= 1 else int(r.value)
                        except: pass

            resolution = "SD"
            if section_type == "movie" and item.media:
                try:
                    res = str(item.media[0].videoResolution).upper()
                    resolution = res + "P" if res.isdigit() else res
                except: pass

            raw_genres = [g.tag for g in item.genres] if item.genres else []
            normalized_genres = sorted(list(set([self._normalize_genre(g) for g in raw_genres])))
            
            director = "Inconnu"
            if section_type == "movie" and hasattr(item, 'directors') and item.directors:
                director = item.directors[0].tag

            # Extraction Cast
            cast_list = []
            # if hasattr(item, 'roles'):
            #     for role in item.roles[:10]: # Limite à 10 acteurs
            #         cast_list.append({
            #             "name": role.tag,
            #             "role": role.role or "",
            #             "thumb": role.thumb
            #         })

            # Extraction Audio & Subtitles & Badges
            audio_tracks = []
            subtitles = []
            badges = set()
            
            # Resolution Badge
            if resolution != "SD": badges.add(resolution)
            
            if hasattr(item, 'media') and item.media:
                media = item.media[0]
                
                # HDR Detection
                if hasattr(media, 'videoProfile') and media.videoProfile == "main 10":
                     badges.add("HDR")
                
                if hasattr(media, 'parts') and media.parts:
                    part = media.parts[0]
                    if hasattr(part, 'streams'):
                        for stream in part.streams:
                            if stream.streamType == 2: # Audio
                                title_disp = stream.displayTitle or stream.title or "Unknown"
                                codec = stream.codec or "unknown"
                                if "atmos" in title_disp.lower() or "atmos" in codec.lower():
                                    badges.add("Atmos")
                                
                                audio_tracks.append({
                                    "display_title": title_disp,
                                    "language": stream.languageCode or "und",
                                    "codec": codec,
                                    "channels": stream.channels or 2,
                                    "forced": getattr(stream, 'forced', False)
                                })
                            elif stream.streamType == 3: # Subtitle
                                subtitles.append({
                                    "display_title": stream.displayTitle or stream.title or "Unknown",
                                    "language": stream.languageCode or "und",
                                    "codec": stream.codec or "unknown",
                                    "forced": getattr(stream, 'forced', False)
                                })

            # Chapters & Markers
            chapters_list = []
            markers_list = []
            
            if hasattr(item, 'chapters') and item.chapters:
                 for chap in item.chapters:
                     chapters_list.append({
                         "title": chap.title or f"Chapter {item.chapters.index(chap)+1}",
                         "start_time": chap.start,
                         "end_time": chap.end,
                         "thumb": chap.thumb
                     })
            
            if hasattr(item, 'markers') and item.markers:
                for m in item.markers:
                    markers_list.append({
                        "title": m.type, "type": m.type, 
                        "start_time": m.start, "end_time": m.end
                    })

            # View State
            view_offset = item.viewOffset if hasattr(item, 'viewOffset') else 0
            view_count = item.viewCount if hasattr(item, 'viewCount') else 0

            self.raw_cache[key].append({
                "play_id": str(uuid.uuid4()), 
                "type": section_type, 
                "title": item.title,
                "year": item.year or 0, 
                "added_at": item.addedAt.isoformat() if hasattr(item, 'addedAt') and item.addedAt else None,
                "content_rating": getattr(item, 'contentRating', None),
                "studio": getattr(item, 'studio', None),
                "thumb": item.thumb, 
                "art": item.art, # Backdrop
                "rating": round(float(item.rating), 1) if item.rating else 0.0,
                "imdb_rating": imdb_rating,
                "rotten_rating": rotten_rating,
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
                "duration": item.duration or 0, # Runtime
                # "cast": cast_list,
                "badges": list(badges),
                "audio_tracks": audio_tracks,
                "subtitles": subtitles,
                "chapters": chapters_list,
                "markers": markers_list,
                "view_offset": view_offset,
                "view_count": view_count,
                "episodes": episodes_data,
                "labels": labels,
                # "trailers": trailers_list # On évite de surcharger le scan global avec les trailers pour l'instant
                # On les chargera à la demande via /movies/{id} ou on fera un update spécifique
            })
            logger.info(f"Media Fetched '{item.title}' from {resource.name}")
        except Exception as e:
            logger.warning(f"⚠️ Skip item '{item.title}' (Donnée invalide): {e}")


    def _build_url_params(self, inst, key=None):
        k = key if key else inst['key']
        return f"server={urllib.parse.quote(inst['server_url'])}&path={urllib.parse.quote(k)}&token={inst['server_token']}"

    def _build_api_cache(self):
        """
        Transforme le cache brut (liste d'occurrences pour chaque clé) en objets API finaux (MediaDetail).
        C'est ici que se fait la FUSION (Merging) des sources :
        Un item (ex: 'Inception') peut avoir 3 sources (Serveur A, B, C).
        On crée un seul MediaDetail avec une liste de 3 'sources'.
        """
        new_cache = {}
        for key, instances in self.raw_cache.items():
            main = next((i for i in instances if i['is_owned']), instances[0])
            
            poster_link = ""
            if main['thumb']:
                poster_link = f"/proxy-image?url={urllib.parse.quote(main['server_url'])}&thumb={urllib.parse.quote(main['thumb'])}&token={main['server_token']}"

            backdrop_link = ""
            if main['art']:
                 backdrop_link = f"/proxy-image?url={urllib.parse.quote(main['server_url'])}&thumb={urllib.parse.quote(main['art'])}&token={main['server_token']}&width=1280"

            # Construction Objets Cast
            cast_objs = []
            # for c in main['cast']:
            #     c_thumb = ""
            #     if c['thumb']:
            #          c_thumb = f"/proxy-image?url={urllib.parse.quote(main['server_url'])}&thumb={urllib.parse.quote(c['thumb'])}&token={main['server_token']}&width=300"
            #     cast_objs.append(CastMember(name=c['name'], role=c['role'], thumb_url=c_thumb))

            # Construction Objets Chapters
            chapter_objs = []
            for chap in main['chapters']:
                chap_thumb = ""
                if chap['thumb']:
                     chap_thumb = f"/proxy-image?url={urllib.parse.quote(main['server_url'])}&thumb={urllib.parse.quote(chap['thumb'])}&token={main['server_token']}&width=400"
                chapter_objs.append(Chapter(
                    title=chap['title'], start_time=chap['start_time'], 
                    end_time=chap['end_time'], thumb_url=chap_thumb
                ))

            # Construction Markers
            marker_objs = []
            if 'markers' in main:
                for m in main['markers']:
                    marker_objs.append(Marker(
                        title=m['title'], type=m['type'], 
                        start_time=m['start_time'], end_time=m['end_time']
                    ))

            media_item = MediaDetail(
                id=key, type=main['type'], title=main['title'], year=main['year'],
                added_at=main['added_at'], content_rating=main['content_rating'],
                studio=main['studio'], director=main['director'], genres=main['genres'], 
                summary=main['summary'], rating=main['rating'],
                imdb_rating=main.get('imdb_rating'), rotten_rating=main.get('rotten_rating'),
                poster_url=poster_link,
                backdrop_url=backdrop_link,
                runtime=main['duration'], badges=main['badges'],
                chapters=chapter_objs,
                markers=marker_objs,
                view_offset=main.get('view_offset', 0),
                view_count=main.get('view_count', 0),
                audio_tracks=[AudioTrack(**a) for a in main['audio_tracks']],
                subtitles=[Subtitle(**s) for s in main['subtitles']],
                labels=main.get('labels', [])
            )

            if main['type'] == 'movie':
                for inst in instances:
                    # Merge Badges (4K from one source, HDR from another...)
                    # (Simplification: on prend ceux du main pour l'instant, ou on pourrait merger)
                    
                    params = self._build_url_params(inst)
                    media_item.sources.append(Source(
                        server_name=inst['server_name'], resolution=inst['resolution'],
                        is_owned=inst['is_owned'], 
                        stream_url=f"/vlc-stream/{inst['play_id']}?{params}",
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
                        
                        if e_idx not in seasons_map[s_idx]:
                            t_url = f"/proxy-image?url={urllib.parse.quote(inst['server_url'])}&thumb={urllib.parse.quote(ep['thumb'])}&token={inst['server_token']}" if ep['thumb'] else ""
                            seasons_map[s_idx][e_idx] = EpisodeDetail(
                                id=f"S{s_idx:02d}E{e_idx:02d}", index=e_idx, title=ep['title'],
                                summary=ep['summary'], thumb_url=t_url
                            )
                        
                        res = "SD"
                        try:
                            if ep['media']:
                                r = str(ep['media'][0].videoResolution).upper()
                                res = r + "P" if r.isdigit() else r
                        except: pass

                        play_id = str(uuid.uuid4())
                        eparams = self._build_url_params(inst, key=ep['key'])
                        seasons_map[s_idx][e_idx].sources.append(Source(
                            server_name=inst['server_name'], resolution=res, is_owned=inst['is_owned'],
                            stream_url=f"/vlc-stream/{play_id}?{eparams}",
                            m3u_url=f"/playlist/{play_id}.m3u?{eparams}&title={urllib.parse.quote(inst['title'] + ' ' + ep['title'])}",
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