"""
Extensions pour PlexClient - Nouvelles fonctionnalités
Récemment Ajouté, Historique, Sessions Actives, etc.
"""
import asyncio
import logging
import urllib.parse
import time
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from app.models import (
    MediaDetail, HistoryEntry, ClientInfo, SessionInfo,
    Trailer, HistoryEntry
)

logger = logging.getLogger("PlexExtensions")

class PlexExtensions:
    """Extensions des fonctionnalités PlexClient"""
    
    # =========================================================================
    # 1. RECENTLY ADDED - Récemment Ajouté
    # =========================================================================
    
    async def get_recently_added(self, limit: int = 50) -> Dict[str, MediaDetail]:
        """
        Récupère les X derniers médias ajoutés à tous les serveurs.
        
        Args:
            limit: Nombre d'items à retourner
            
        Returns:
            Dict avec MediaDetail pour chaque item
        """
        if not hasattr(self, 'raw_cache'):
            logger.error("❌ raw_cache non trouvé")
            return {}
            
        recently_added = {}
        try:
            from plexapi.myplex import MyPlexAccount
            logger.info(f"🔍 [Recently Added] Authentification MyPlexAccount...")
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            target_resources = [r for r in resources if "server" in r.provides]
            logger.info(f"📊 [Recently Added] {len(target_resources)} serveurs trouvés")
            
            if self.settings.ONLY_OWNED:
                target_resources = [r for r in target_resources if r.owned]
                logger.info(f"📊 [Recently Added] Filtré à {len(target_resources)} serveurs possédés")
            
            for resource in target_resources:
                try:
                    logger.info(f"🔌 [Recently Added] Connexion à {resource.name}...")
                    server = await asyncio.to_thread(resource.connect, timeout=10)
                    sections = await asyncio.to_thread(server.library.sections)
                    logger.debug(f"📚 [Recently Added] {len(sections)} sections trouvées sur {resource.name}")
                    
                    for section in sections:
                        if section.type not in ["movie", "show"]:
                            continue
                        
                        logger.info(f"   🎬 [Recently Added] Récupération {limit} items de '{section.title}' ({section.type})...")
                        items = await asyncio.to_thread(
                            section.recentlyAdded, 
                            maxresults=limit
                        )
                        logger.info(f"   ✅ [Recently Added] {len(items)} items récupérés de '{section.title}'")
                        
                        for item in items:
                            key = f"{item.title}-{item.year}" if not item.ratingKey else str(item.ratingKey)
                            if key not in recently_added:
                                logger.debug(f"   📝 [Recently Added] Traitement: {item.title} ({item.year})")
                                media_detail = await self._item_to_media_detail(
                                    item, section.type, resource, server
                                )
                                recently_added[key] = media_detail
                                
                except Exception as e:
                    logger.warning(f"⚠️ [Recently Added] Erreur sur {resource.name}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ [Recently Added] Erreur globale: {e}")
        
        logger.info(f"✨ [Recently Added] Total: {len(recently_added)} médias uniques")
        return recently_added
    
    # =========================================================================
    # 2. WATCH HISTORY - Historique de Lecture
    # =========================================================================
    
    async def get_watch_history(
        self, 
        limit: int = 100, 
        days_back: int = 30
    ) -> List[HistoryEntry]:
        """
        Récupère l'historique de lecture.
        
        Args:
            limit: Nombre d'entrées à retourner
            days_back: Nombre de jours à consulter
            
        Returns:
            Liste des HistoryEntry triée par date récente
        """
        history_entries = []
        logger.info(f"🔍 [Watch History] Récupération sur les {days_back} derniers jours, limit={limit}")
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            logger.info(f"📊 [Watch History] {len(resources)} ressources trouvées")
            
            # Convertir datetime en timestamp Unix (en secondes, pas millisecondes)
            min_date_timestamp = int((datetime.now() - timedelta(days=days_back)).timestamp())
            logger.debug(f"⏰ [Watch History] Min timestamp: {min_date_timestamp}")
            
            for resource in resources:
                if "server" not in resource.provides:
                    continue
                try:
                    logger.info(f"🔌 [Watch History] Connexion à {resource.name}...")
                    server = await asyncio.to_thread(resource.connect, timeout=10)
                    logger.debug(f"   📡 URL: {server.baseurl}")
                    history = await asyncio.to_thread(
                        server.library.history,
                        maxresults=limit,
                        mindate=min_date_timestamp  # Passer timestamp Unix, pas datetime
                    )
                    logger.info(f"   ✅ [Watch History] {len(history)} entrées récupérées")
                    
                    for item in history:
                        try:
                            logger.debug(f"   📝 [History] {item.title} - {item.type}")
                            # lastViewedAt est un timestamp Unix (int)
                            watched_at = datetime.fromtimestamp(item.lastViewedAt) if hasattr(item, 'lastViewedAt') and isinstance(item.lastViewedAt, (int, float)) else datetime.now()
                            
                            thumb_url = ""
                            if hasattr(item, 'thumb') and item.thumb:
                                thumb_url = f"/proxy-image?url={urllib.parse.quote(server._baseurl)}&thumb={urllib.parse.quote(item.thumb)}&token={resource.accessToken}&width=300"
                            
                            entry = HistoryEntry(
                                id=str(item.ratingKey),
                                title=item.title,
                                type=item.type,
                                watched_at=watched_at,
                                view_offset=getattr(item, 'viewOffset', 0),
                                duration=getattr(item, 'duration', 0),
                                thumb_url=thumb_url
                            )
                            history_entries.append(entry)
                            logger.debug(f"   ✔️ Ajouté: {item.title}")
                        except Exception as e:
                            logger.debug(f"⚠️ Erreur parsing item historique: {e}")
                            
                except Exception as e:
                    logger.warning(f"⚠️ [Watch History] Erreur sur {resource.name}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ [Watch History] Erreur globale: {e}")
        
        # Trier par date décroissante (plus récent en premier)
        history_entries.sort(key=lambda x: x.watched_at, reverse=True)
        return history_entries[:limit]
    
    # =========================================================================
    # 3. ACTIVE SESSIONS - Sessions Actives (Qui regarde quoi)
    # =========================================================================
    
    async def get_active_sessions(self) -> List[SessionInfo]:
        """
        Récupère les médias actuellement en cours de lecture.
        
        Returns:
            Liste des SessionInfo pour chaque lecture active
        """
        sessions = []
        logger.info(f"🔍 [Active Sessions] Récupération des sessions actives...")
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            logger.info(f"📊 [Active Sessions] {len(resources)} ressources trouvées")
            
            for resource in resources:
                if "server" not in resource.provides:
                    continue
                try:
                    logger.info(f"🔌 [Active Sessions] Connexion à {resource.name}...")
                    server = await asyncio.to_thread(resource.connect, timeout=10)
                    active_sessions = await asyncio.to_thread(server.sessions)
                    logger.info(f"   ✅ [Active Sessions] {len(active_sessions)} sessions actives trouvées")
                    
                    for session in active_sessions:
                        try:
                            user = session.usernames[0] if hasattr(session, 'usernames') and session.usernames else "Unknown"
                            logger.debug(f"   👤 [Session] Utilisateur: {user}")
                            logger.debug(f"   🎬 [Session] Titre: {session.title}")
                            logger.debug(f"   📺 [Session] Type: {session.type}")
                            
                            progress = 0
                            if hasattr(session, 'duration') and session.duration and session.duration > 0:
                                progress = (session.viewOffset / session.duration) * 100 if hasattr(session, 'viewOffset') else 0
                            logger.debug(f"   ⏱️ [Session] Progression: {progress:.1f}% ({session.viewOffset}/{session.duration})")
                            
                            client_name = session.players[0].title if hasattr(session, 'players') and session.players else "Unknown"
                            logger.debug(f"   🖥️ [Session] Client: {client_name}")
                            
                            session_info = SessionInfo(
                                user=user,
                                media_title=session.title,
                                media_type=session.type,
                                progress_percent=progress,
                                view_offset=getattr(session, 'viewOffset', 0),
                                duration=getattr(session, 'duration', 0),
                                client_name=client_name
                            )
                            sessions.append(session_info)
                        except Exception as e:
                            logger.debug(f"⚠️ [Session] Erreur parsing session: {e}")
                            
                except Exception as e:
                    logger.warning(f"⚠️ [Active Sessions] Erreur sur {resource.name}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ [Active Sessions] Erreur globale: {e}")
        
        logger.info(f"✨ [Active Sessions] Total: {len(sessions)} sessions")
        return sessions
    
    # =========================================================================
    # 4. CONNECTED CLIENTS - Clients Connectés
    # =========================================================================
    
    async def get_connected_clients(self) -> List[ClientInfo]:
        """
        Récupère la liste des clients connectés au serveur.
        
        Returns:
            Liste des ClientInfo pour chaque client
        """
        clients = []
        logger.info(f"🔍 [Connected Clients] Récupération des clients connectés...")
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            logger.debug(f"✅ Authentification réussie")
            
            if self.settings.SERVER_NAME:
                logger.info(f"📍 Recherche du serveur: {self.settings.SERVER_NAME}")
                resource = await asyncio.to_thread(account.resource, self.settings.SERVER_NAME)
            else:
                logger.debug(f"📍 Recherche du premier serveur disponible...")
                resources = await asyncio.to_thread(account.resources)
                resource = next((r for r in resources if "server" in r.provides), None)
            
            if resource:
                logger.info(f"🔌 Connexion à {resource.name}...")
                server = await asyncio.to_thread(resource.connect, timeout=10)
                plex_clients = await asyncio.to_thread(server.clients)
                logger.info(f"✅ {len(plex_clients)} clients trouvés")
                
                for client in plex_clients:
                    try:
                        logger.debug(f"   🖥️ [Client] {client.title}")
                        logger.debug(f"      Platform: {getattr(client, 'platform', 'unknown')}")
                        logger.debug(f"      Device Class: {getattr(client, 'deviceClass', 'unknown')}")
                        logger.debug(f"      Disponible: {client.isAvailable if hasattr(client, 'isAvailable') else 'N/A'}")
                        
                        client_info = ClientInfo(
                            name=client.title,
                            device_class=getattr(client, 'deviceClass', 'unknown'),
                            platform=getattr(client, 'platform', 'unknown'),
                            is_available=client.isAvailable if hasattr(client, 'isAvailable') else False,
                            is_playing=False  # À améliorer avec les sessions
                        )
                        clients.append(client_info)
                        logger.debug(f"      ✔️ Ajouté au résultat")
                    except Exception as e:
                        logger.debug(f"⚠️ [Client] Erreur parsing: {e}")
            else:
                logger.warning(f"⚠️ [Connected Clients] Aucun serveur trouvé")
                        
        except Exception as e:
            logger.error(f"❌ [Connected Clients] Erreur globale: {e}")
        
        logger.info(f"✨ [Connected Clients] Total: {len(clients)} clients")
        return clients
    
    # =========================================================================
    # 5. TRAILERS - Trailers Disponibles
    # =========================================================================
    
    async def _get_trailers(self, item, server, resource) -> List[Trailer]:
        """
        Récupère les trailers disponibles pour un média.
        
        Args:
            item: Objet Plex (Movie ou Show)
            server: Serveur Plex
            resource: Resource Plex
            
        Returns:
            Liste des Trailer disponibles
        """
        trailers = []
        try:
            if hasattr(item, 'extras'):
                extras = await asyncio.to_thread(item.extras)
                
                for extra in extras[:5]:  # Limiter aux 5 premiers
                    try:
                        if hasattr(extra, 'subtype') and extra.subtype == 'trailer':
                            thumb_url = ""
                            if hasattr(extra, 'thumb') and extra.thumb:
                                thumb_url = f"/proxy-image?url={urllib.parse.quote(server._baseurl)}&thumb={urllib.parse.quote(extra.thumb)}&token={resource.accessToken}&width=300"
                            
                            trailer = Trailer(
                                title=extra.title,
                                duration=getattr(extra, 'duration', 0),
                                thumb_url=thumb_url,
                                key=getattr(extra, 'key', None)
                            )
                            trailers.append(trailer)
                    except Exception as e:
                        logger.debug(f"⚠️ Erreur parsing trailer: {e}")
        except Exception as e:
            logger.debug(f"⚠️ Erreur récupération trailers: {e}")
        
        return trailers
    
    # =========================================================================
    # 6. TAGS & LABELS - Tags Personnalisés
    # =========================================================================
    
    async def add_label(self, media_id: str, label: str) -> bool:
        """Ajoute un label à un média (ex: Favoris, 4K UHD)"""
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resource = await asyncio.to_thread(account.resource, self.settings.SERVER_NAME)
            server = await asyncio.to_thread(resource.connect, timeout=10)
            
            item = await asyncio.to_thread(server.fetchItem, media_id)
            await asyncio.to_thread(item.addLabel, label)
            logger.info(f"✅ Label '{label}' ajouté à {item.title}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur add_label: {e}")
            return False
    
    async def remove_label(self, media_id: str, label: str) -> bool:
        """Retire un label d'un média"""
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resource = await asyncio.to_thread(account.resource, self.settings.SERVER_NAME)
            server = await asyncio.to_thread(resource.connect, timeout=10)
            
            item = await asyncio.to_thread(server.fetchItem, media_id)
            await asyncio.to_thread(item.removeLabel, label)
            logger.info(f"✅ Label '{label}' retiré de {item.title}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur remove_label: {e}")
            return False
    
    # =========================================================================
    # 7. ÉDITION MÉTADONNÉES
    # =========================================================================
    
    async def mark_as_favorite(self, media_id: str) -> bool:
        """Marquer un média comme favori (ajoute label 'Favoris')"""
        return await self.add_label(media_id, "Favoris")
    
    async def remove_from_favorites(self, media_id: str) -> bool:
        """Retirer un média des favoris"""
        return await self.remove_label(media_id, "Favoris")
    
    async def rate_media(self, media_id: str, rating: float) -> bool:
        """
        Noter un média (0-10).
        
        Args:
            media_id: ID du média
            rating: Note entre 0 et 10
        """
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resource = await asyncio.to_thread(account.resource, self.settings.SERVER_NAME)
            server = await asyncio.to_thread(resource.connect, timeout=10)
            
            item = await asyncio.to_thread(server.fetchItem, media_id)
            await asyncio.to_thread(item.editUserRating, rating)
            logger.info(f"✅ Note {rating}/10 donnée à {item.title}")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur rate_media: {e}")
            return False
    
    # =========================================================================
    # 8. RECHERCHE AVANCÉE
    # =========================================================================
    
    async def advanced_search(
        self,
        title: Optional[str] = None,
        year: Optional[int] = None,
        unwatched: Optional[bool] = None,
        sort: str = 'rating:desc',
        filters: Optional[Dict] = None,
        limit: int = 50
    ) -> Dict[str, MediaDetail]:
        """
        Recherche avancée dans les films.
        
        Args:
            title: Titre à chercher
            year: Année
            unwatched: Si True, retourne seulement les non vus
            sort: Tri ('rating:desc', 'title:asc', 'year:desc')
            filters: Dict avec filtres supplémentaires {'genre': 'action'}
            limit: Nombre max de résultats
        """
        results = {}
        logger.info(f"🔍 [Advanced Search] Recherche: title={title}, year={year}, unwatched={unwatched}, sort={sort}, filters={filters}")
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            logger.info(f"📊 [Advanced Search] {len(resources)} ressources trouvées")
            
            for resource in resources:
                if "server" not in resource.provides:
                    continue
                try:
                    logger.info(f"🔌 [Advanced Search] Connexion à {resource.name}...")
                    server = await asyncio.to_thread(resource.connect, timeout=10)
                    sections = await asyncio.to_thread(server.library.sections)
                    logger.debug(f"   📚 {len(sections)} sections trouvées")
                    
                    for section in sections:
                        if section.type not in ["movie", "show"]:
                            continue
                        
                        search_kwargs = {
                            'sort': sort,
                            'limit': limit
                        }
                        if title:
                            search_kwargs['title'] = title
                        if year:
                            search_kwargs['year'] = year
                        if unwatched:
                            search_kwargs['unwatched'] = True
                        if filters:
                            search_kwargs.update(filters)
                        
                        logger.info(f"   🔎 [Advanced Search] Recherche dans '{section.title}' ({section.type})...")
                        items = await asyncio.to_thread(section.search, **search_kwargs)
                        logger.info(f"   ✅ {len(items)} résultats trouvés")
                        
                        for item in items:
                            logger.debug(f"   📝 {item.title} ({item.year})")
                            key = f"{item.title}-{item.year}"
                            if key not in results:
                                media_detail = await self._item_to_media_detail(
                                    item, section.type, resource, server
                                )
                                results[key] = media_detail
                                
                except Exception as e:
                    logger.debug(f"⚠️ [Advanced Search] Erreur sur {resource.name}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ [Advanced Search] Erreur globale: {e}")
        
        logger.info(f"✨ [Advanced Search] Total: {len(results)} résultats")
        return results
    
    # =========================================================================
    # 9. HUBS - Découverte Algorithmique
    # =========================================================================
    
    async def get_discovery_hubs(self, limit: int = 10) -> Dict[str, List[MediaDetail]]:
        """
        Récupère les hubs de découverte (algorithme Plex).
        
        Returns:
            Dict avec hub_title -> liste de MediaDetail
        """
        hubs_dict = {}
        logger.info(f"🔍 [Discovery Hubs] Récupération des hubs de découverte (limit={limit})...")
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resources = await asyncio.to_thread(account.resources)
            logger.info(f"📊 [Discovery Hubs] {len(resources)} ressources trouvées")
            
            for resource in resources:
                if "server" not in resource.provides:
                    continue
                try:
                    logger.info(f"🔌 [Discovery Hubs] Connexion à {resource.name}...")
                    server = await asyncio.to_thread(resource.connect, timeout=10)
                    hubs = await asyncio.to_thread(server.library.hubs)
                    logger.info(f"   ✅ {len(hubs)} hubs trouvés")
                    
                    for hub in hubs[:10]:
                        try:
                            logger.debug(f"   🎯 [Hub] {hub.title}")
                            hub_items = []
                            if hasattr(hub, 'items'):
                                logger.debug(f"      Nombre d'items dans ce hub: {len(hub.items) if hub.items else 0}")
                                items = hub.items[:limit] if hub.items else []
                                logger.debug(f"      Traitement des {len(items)} premiers items...")
                                for item in items:
                                    try:
                                        logger.debug(f"         📝 {item.title}")
                                        media_detail = await self._item_to_media_detail(
                                            item, 
                                            getattr(item, 'type', 'movie'),
                                            resource, 
                                            server
                                        )
                                        hub_items.append(media_detail)
                                    except Exception as e:
                                        logger.debug(f"         ⚠️ Erreur: {e}")
                            
                            if hub_items and hub.title not in hubs_dict:
                                logger.debug(f"      ✔️ Hub '{hub.title}' ajouté avec {len(hub_items)} items")
                                hubs_dict[hub.title] = hub_items
                        except Exception as e:
                            logger.debug(f"⚠️ [Discovery Hubs] Erreur parsing hub: {e}")
                            
                except Exception as e:
                    logger.warning(f"⚠️ [Discovery Hubs] Erreur sur {resource.name}: {e}")
                    
        except Exception as e:
            logger.error(f"❌ [Discovery Hubs] Erreur globale: {e}")
        
        logger.info(f"✨ [Discovery Hubs] Total: {len(hubs_dict)} hubs avec contenu")
        return hubs_dict
    
    # =========================================================================
    # 14. TRANSCODAGE & OPTIMISATION
    # =========================================================================

    async def optimize_media(self, media_id: str, target: str = "mobile", quality: int = 10) -> bool:
        """
        Lance une tâche d'optimisation (transcodage) pour un média.
        
        Args:
            media_id: ID du média
            target: 'mobile', 'tv'
            quality: Qualité (Mbps)
        """
        try:
            from plexapi.myplex import MyPlexAccount
            account = await asyncio.to_thread(MyPlexAccount, token=self.settings.PLEX_TOKEN)
            resource = await asyncio.to_thread(account.resource, self.settings.SERVER_NAME)
            server = await asyncio.to_thread(resource.connect, timeout=10)
            
            item = await asyncio.to_thread(server.fetchItem, media_id)
            
            # Note: plexapi optimize n'est pas toujours 100% documenté ou stable via API
            # On tente l'appel standard
            await asyncio.to_thread(
                item.optimize,
                target=target,
                deviceProfile='Android' if target == 'mobile' else 'Android TV',
                videoQuality=quality
            )
            logger.info(f"✅ Optimisation lancée pour {item.title} ({target})")
            return True
        except Exception as e:
            logger.error(f"❌ Erreur optimize_media: {e}")
            return False

    # =========================================================================
    # HELPER - Conversion Item à MediaDetail
    # =========================================================================
    
    async def _item_to_media_detail(
        self,
        item,
        section_type: str,
        resource,
        server
    ) -> MediaDetail:
        """
        Convertit un objet item Plex en MediaDetail complet.
        Réutilise la logique de _process_item mais en async.
        """
        import urllib.parse
        
        poster_url = ""
        if hasattr(item, 'thumb') and item.thumb:
            poster_url = f"/proxy-image?url={urllib.parse.quote(server._baseurl)}&thumb={urllib.parse.quote(item.thumb)}&token={resource.accessToken}&width=400"
        
        backdrop_url = ""
        if hasattr(item, 'art') and item.art:
            backdrop_url = f"/proxy-image?url={urllib.parse.quote(server._baseurl)}&thumb={urllib.parse.quote(item.art)}&token={resource.accessToken}&width=1280"
        
        # Récupération des Trailers (Feature 9)
        trailers = []
        try:
             trailers = await self._get_trailers(item, server, resource)
        except Exception: pass

        # Récupération des Labels (Feature 10)
        labels = []
        if hasattr(item, 'labels'):
            labels = [l.tag for l in item.labels]

        # Gestion sécurisée des dates (peuvent être datetime ou int/timestamp)
        try:
            if isinstance(item.addedAt, datetime):
                added_at = item.addedAt
            elif isinstance(item.addedAt, (int, float)):
                added_at = datetime.fromtimestamp(item.addedAt)
            else:
                added_at = datetime.now()
        except:
            added_at = datetime.now()

        try:
            if isinstance(item.lastViewedAt, datetime):
                last_viewed_at = item.lastViewedAt
            elif isinstance(item.lastViewedAt, (int, float)):
                last_viewed_at = datetime.fromtimestamp(item.lastViewedAt)
            else:
                last_viewed_at = None
        except:
            last_viewed_at = None

        media_detail = MediaDetail(
            id=str(item.ratingKey) if hasattr(item, 'ratingKey') else item.title,
            type=section_type,
            title=item.title,
            year=item.year or 0,
            added_at=added_at,
            summary=getattr(item, 'summary', ''),
            rating=float(item.rating) if hasattr(item, 'rating') and item.rating else 0.0,
            poster_url=poster_url,
            backdrop_url=backdrop_url,
            runtime=int(getattr(item, 'duration', 0) / 60000) if hasattr(item, 'duration') else 0,
            view_count=getattr(item, 'viewCount', 0),
            view_offset=getattr(item, 'viewOffset', 0),
            last_viewed_at=last_viewed_at,
            trailers=trailers,
            labels=labels,
            content_rating=getattr(item, 'contentRating', None),
            studio=getattr(item, 'studio', None)
        )
        
        return media_detail
        return media_detail
