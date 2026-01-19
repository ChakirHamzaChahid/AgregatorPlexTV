"""
Tests des endpoints API REST du serveur PlexHub.

Couvre:
- GET /servers
- GET /collections
- GET /continue_watching
- POST /actions/scrobble
- POST /actions/progress
- GET /recently-added
- GET /watch-history
- GET /now-playing
- GET /clients
- GET /hubs
- GET /search
- POST /favorite/{media_id}
- POST /rate/{media_id}/{rating}
- POST /label/{media_id}/{label}
- DELETE /label/{media_id}/{label}
- POST /optimize/{media_id}
- GET /cache/stats
- POST /cache/clear
- POST /refresh
"""

import pytest
import asyncio
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock, MagicMock
from datetime import datetime, timedelta

from app.main import app, _api_cache
from app.models import (
    ServerInfo, Collection, HistoryEntry, MediaDetail, 
    ActiveSession, ClientInfo, Source
)

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """Client de test FastAPI"""
    return TestClient(app)

@pytest.fixture
def mock_plex_client():
    """Mock du PlexClient pour les tests"""
    with patch('app.main.plex_client') as mock:
        yield mock

@pytest.fixture(autouse=True)
def clear_cache():
    """Nettoie le cache avant chaque test"""
    _api_cache.clear()
    yield
    _api_cache.clear()

# =============================================================================
# FIXTURES DONNÉES
# =============================================================================

@pytest.fixture
def sample_server_info():
    """Données serveur pour les tests"""
    return ServerInfo(
        name="Mon Serveur",
        url="http://192.168.1.100:32400",
        plex_pass=True,
        owned=True,
        is_available=True
    )

@pytest.fixture
def sample_collection():
    """Données collection pour les tests"""
    return Collection(
        id="col-123",
        title="Ma Collection",
        summary="Description collection",
        poster_url="/proxy-image?thumb=/library/metadata/123/thumb",
        backdrop_url="/proxy-image?thumb=/library/metadata/123/art",
        item_count=42
    )

@pytest.fixture
def sample_media_detail():
    """Données média détaillé pour les tests"""
    return MediaDetail(
        id="tt1375666",
        title="Inception",
        type="movie",
        year=2010,
        rating=8.8,
        poster_url="/proxy-image?thumb=/library/metadata/123/thumb",
        backdrop_url="/proxy-image?thumb=/library/metadata/123/art",
        summary="Un voleur doit infiltrer l'esprit de cibles...",
        runtime=148,
        genres=["Action", "Sci-Fi", "Thriller"],
        director="Christopher Nolan",
        writer="Christopher Nolan",
        content_rating="PG-13",
        studio="Warner Bros",
        added_at=datetime.now(),
        updated_at=datetime.now(),
        watched=False,
        watched_at=None,
        progress_percent=0,
        markers=[],
        labels=[],
        chapters=[],
        cast=[],
        sources=[
            Source(
                server_name="Mon Serveur",
                resolution="1080P",
                is_owned=True,
                stream_url="/vlc-stream/tt1375666",
                m3u_url="/playlist/tt1375666.m3u",
                plex_deeplink="plex://preplay/tt1375666"
            )
        ],
        seasons=[]
    )

@pytest.fixture
def sample_active_session():
    """Données session active pour les tests"""
    return ActiveSession(
        id="session-123",
        user="John Doe",
        media_title="Inception",
        media_type="movie",
        progress_percent=45.5,
        client_name="VLC"
    )

@pytest.fixture
def sample_client_info():
    """Données client Plex pour les tests"""
    return ClientInfo(
        name="Living Room TV",
        device_class="pc",
        platform="Windows",
        is_available=True
    )

@pytest.fixture
def sample_history_entry():
    """Données entrée historique pour les tests"""
    return HistoryEntry(
        id="tt1375666",
        title="Inception",
        type="movie",
        year=2010,
        thumb_url="/proxy-image?thumb=/library/metadata/123/thumb",
        last_watched_at=datetime.now()
    )

# =============================================================================
# TESTS: GET /servers
# =============================================================================

class TestGetServers:
    """Tests de GET /api/servers"""
    
    def test_get_servers_success(self, client, mock_plex_client, sample_server_info):
        """Test récupération serveurs avec succès"""
        mock_plex_client.get_connected_servers.return_value = [sample_server_info]
        
        response = client.get("/api/servers")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Mon Serveur"
        assert data[0]["plex_pass"] is True
        assert data[0]["is_available"] is True

    def test_get_servers_empty(self, client, mock_plex_client):
        """Test quand aucun serveur disponible"""
        mock_plex_client.get_connected_servers.return_value = []
        
        response = client.get("/api/servers")
        
        assert response.status_code == 200
        assert response.json() == []

    def test_get_servers_error_handling(self, client, mock_plex_client):
        """Test gestion des erreurs lors de la récupération"""
        mock_plex_client.get_connected_servers.side_effect = Exception("Connection error")
        
        response = client.get("/api/servers")
        
        # FastAPI retourne 500 en cas d'exception non gérée
        assert response.status_code >= 400

# =============================================================================
# TESTS: GET /collections
# =============================================================================

class TestGetCollections:
    """Tests de GET /api/collections"""
    
    @pytest.mark.asyncio
    async def test_get_collections_success(self, client, mock_plex_client, sample_collection):
        """Test récupération collections avec succès"""
        mock_plex_client.get_collections = AsyncMock(return_value=[sample_collection])
        
        response = client.get("/api/collections")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Ma Collection"
        assert data[0]["item_count"] == 42

    @pytest.mark.asyncio
    async def test_get_collections_empty(self, client, mock_plex_client):
        """Test quand aucune collection"""
        mock_plex_client.get_collections = AsyncMock(return_value=[])
        
        response = client.get("/api/collections")
        
        assert response.status_code == 200
        assert response.json() == []

# =============================================================================
# TESTS: GET /continue_watching
# =============================================================================

class TestGetContinueWatching:
    """Tests de GET /api/continue_watching"""
    
    @pytest.mark.asyncio
    async def test_get_continue_watching_success(self, client, mock_plex_client, sample_media_detail):
        """Test récupération continue watching"""
        mock_plex_client.get_on_deck = AsyncMock(return_value=[sample_media_detail])
        
        response = client.get("/api/continue_watching")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Inception"

    @pytest.mark.asyncio
    async def test_get_continue_watching_empty(self, client, mock_plex_client):
        """Test quand rien en cours de lecture"""
        mock_plex_client.get_on_deck = AsyncMock(return_value=[])
        
        response = client.get("/api/continue_watching")
        
        assert response.status_code == 200
        assert response.json() == []

# =============================================================================
# TESTS: POST /actions/scrobble
# =============================================================================

class TestScrobbleAction:
    """Tests de POST /api/actions/scrobble"""
    
    @pytest.mark.asyncio
    async def test_scrobble_mark_watched(self, client, mock_plex_client):
        """Test marquage comme vu"""
        mock_plex_client.action_scrobble = AsyncMock(return_value=True)
        
        response = client.post("/api/actions/scrobble", json={
            "key": "rating-key-123",
            "action": "watched"
        })
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        mock_plex_client.action_scrobble.assert_called_once()

    @pytest.mark.asyncio
    async def test_scrobble_mark_unwatched(self, client, mock_plex_client):
        """Test marquage comme non vu"""
        mock_plex_client.action_scrobble = AsyncMock(return_value=True)
        
        response = client.post("/api/actions/scrobble", json={
            "key": "rating-key-123",
            "action": "unwatched"
        })
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_scrobble_missing_action(self, client):
        """Test erreur sans action spécifiée"""
        response = client.post("/api/actions/scrobble", json={
            "key": "rating-key-123"
        })
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_scrobble_failure(self, client, mock_plex_client):
        """Test erreur lors du scrobble"""
        mock_plex_client.action_scrobble = AsyncMock(return_value=False)
        
        response = client.post("/api/actions/scrobble", json={
            "key": "rating-key-123",
            "action": "watched"
        })
        
        assert response.status_code == 500

# =============================================================================
# TESTS: POST /actions/progress
# =============================================================================

class TestUpdateProgress:
    """Tests de POST /api/actions/progress"""
    
    @pytest.mark.asyncio
    async def test_update_progress_success(self, client, mock_plex_client):
        """Test mise à jour progression"""
        mock_plex_client.action_progress = AsyncMock(return_value=True)
        
        response = client.post("/api/actions/progress", json={
            "key": "rating-key-123",
            "time_ms": 120000  # 2 minutes
        })
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_update_progress_missing_time(self, client):
        """Test erreur sans time spécifiée"""
        response = client.post("/api/actions/progress", json={
            "key": "rating-key-123"
        })
        
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_update_progress_failure(self, client, mock_plex_client):
        """Test erreur lors de la mise à jour"""
        mock_plex_client.action_progress = AsyncMock(return_value=False)
        
        response = client.post("/api/actions/progress", json={
            "key": "rating-key-123",
            "time_ms": 120000
        })
        
        assert response.status_code == 500

# =============================================================================
# TESTS: GET /recently-added
# =============================================================================

class TestRecentlyAdded:
    """Tests de GET /api/recently-added"""
    
    @pytest.mark.asyncio
    async def test_recently_added_default(self, client, mock_plex_client, sample_media_detail):
        """Test récupération derniers médias ajoutés"""
        mock_plex_client.get_recently_added = AsyncMock(
            return_value={"tt1375666": sample_media_detail}
        )
        
        response = client.get("/api/recently-added")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Inception"
        assert data[0]["id"] == "tt1375666"

    @pytest.mark.asyncio
    async def test_recently_added_with_limit(self, client, mock_plex_client, sample_media_detail):
        """Test avec paramètre limit personnalisé"""
        mock_plex_client.get_recently_added = AsyncMock(return_value={})
        
        response = client.get("/api/recently-added?limit=100")
        
        assert response.status_code == 200
        mock_plex_client.get_recently_added.assert_called_with(limit=100)

    @pytest.mark.asyncio
    async def test_recently_added_empty(self, client, mock_plex_client):
        """Test quand aucun média récemment ajouté"""
        mock_plex_client.get_recently_added = AsyncMock(return_value={})
        
        response = client.get("/api/recently-added")
        
        assert response.status_code == 200
        assert response.json() == []

# =============================================================================
# TESTS: GET /watch-history
# =============================================================================

class TestWatchHistory:
    """Tests de GET /api/watch-history"""
    
    @pytest.mark.asyncio
    async def test_watch_history_default(self, client, mock_plex_client, sample_media_detail):
        """Test récupération historique de lecture"""
        mock_plex_client.get_watch_history = AsyncMock(
            return_value={"tt1375666": sample_media_detail}
        )
        
        response = client.get("/api/watch-history")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Inception"
        assert len(data[0]["sources"]) > 0

    @pytest.mark.asyncio
    async def test_watch_history_with_params(self, client, mock_plex_client):
        """Test avec paramètres personnalisés"""
        mock_plex_client.get_watch_history = AsyncMock(return_value={})
        
        response = client.get("/api/watch-history?limit=50&days_back=7")
        
        assert response.status_code == 200
        mock_plex_client.get_watch_history.assert_called_with(limit=50, days_back=7)

    @pytest.mark.asyncio
    async def test_watch_history_empty(self, client, mock_plex_client):
        """Test quand pas d'historique"""
        mock_plex_client.get_watch_history = AsyncMock(return_value={})
        
        response = client.get("/api/watch-history")
        
        assert response.status_code == 200
        assert response.json() == []

# =============================================================================
# TESTS: GET /now-playing
# =============================================================================

class TestNowPlaying:
    """Tests de GET /api/now-playing"""
    
    @pytest.mark.asyncio
    async def test_now_playing_with_sessions(self, client, mock_plex_client, sample_active_session):
        """Test récupération sessions actives"""
        mock_plex_client.get_active_sessions = AsyncMock(return_value=[sample_active_session])
        
        response = client.get("/api/now-playing")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["user"] == "John Doe"
        assert data[0]["media_title"] == "Inception"
        assert data[0]["progress"] == 45  # arrondi à int

    @pytest.mark.asyncio
    async def test_now_playing_empty(self, client, mock_plex_client):
        """Test quand aucune session active"""
        mock_plex_client.get_active_sessions = AsyncMock(return_value=[])
        
        response = client.get("/api/now-playing")
        
        assert response.status_code == 200
        assert response.json() == []

# =============================================================================
# TESTS: GET /clients
# =============================================================================

class TestGetClients:
    """Tests de GET /api/clients"""
    
    @pytest.mark.asyncio
    async def test_get_clients_success(self, client, mock_plex_client, sample_client_info):
        """Test récupération clients Plex"""
        mock_plex_client.get_connected_clients = AsyncMock(return_value=[sample_client_info])
        
        response = client.get("/api/clients")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "Living Room TV"
        assert data[0]["is_available"] is True

    @pytest.mark.asyncio
    async def test_get_clients_empty(self, client, mock_plex_client):
        """Test quand aucun client"""
        mock_plex_client.get_connected_clients = AsyncMock(return_value=[])
        
        response = client.get("/api/clients")
        
        assert response.status_code == 200
        assert response.json() == []

# =============================================================================
# TESTS: GET /hubs
# =============================================================================

class TestGetHubs:
    """Tests de GET /api/hubs"""
    
    @pytest.mark.asyncio
    async def test_get_hubs_success(self, client, mock_plex_client, sample_media_detail):
        """Test récupération hubs de découverte"""
        mock_plex_client.get_discovery_hubs = AsyncMock(return_value={
            "Populaires": [sample_media_detail],
            "Nouveautés": [sample_media_detail]
        })
        
        response = client.get("/api/hubs")
        
        assert response.status_code == 200
        data = response.json()
        assert "Populaires" in data
        assert "Nouveautés" in data

    @pytest.mark.asyncio
    async def test_get_hubs_with_limit(self, client, mock_plex_client):
        """Test avec paramètre limit"""
        mock_plex_client.get_discovery_hubs = AsyncMock(return_value={})
        
        response = client.get("/api/hubs?limit=5")
        
        assert response.status_code == 200
        mock_plex_client.get_discovery_hubs.assert_called_with(limit=5)

# =============================================================================
# TESTS: GET /search
# =============================================================================

class TestAdvancedSearch:
    """Tests de GET /api/search"""
    
    @pytest.mark.asyncio
    async def test_search_by_title(self, client, mock_plex_client, sample_media_detail):
        """Test recherche par titre"""
        mock_plex_client.advanced_search = AsyncMock(
            return_value={"tt1375666": sample_media_detail}
        )
        
        response = client.get("/api/search?title=Inception")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["title"] == "Inception"

    @pytest.mark.asyncio
    async def test_search_by_year(self, client, mock_plex_client, sample_media_detail):
        """Test recherche par année"""
        mock_plex_client.advanced_search = AsyncMock(return_value={})
        
        response = client.get("/api/search?year=2010")
        
        assert response.status_code == 200
        mock_plex_client.advanced_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_unwatched_only(self, client, mock_plex_client, sample_media_detail):
        """Test filtre non vus"""
        mock_plex_client.advanced_search = AsyncMock(return_value={})
        
        response = client.get("/api/search?unwatched=true")
        
        assert response.status_code == 200
        mock_plex_client.advanced_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_with_sort(self, client, mock_plex_client):
        """Test tri des résultats"""
        mock_plex_client.advanced_search = AsyncMock(return_value={})
        
        response = client.get("/api/search?sort=rating:desc&order=desc")
        
        assert response.status_code == 200
        mock_plex_client.advanced_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_empty_results(self, client, mock_plex_client):
        """Test recherche sans résultats"""
        mock_plex_client.advanced_search = AsyncMock(return_value={})
        
        response = client.get("/api/search?title=NonExistentMovie")
        
        assert response.status_code == 200
        assert response.json() == []

# =============================================================================
# TESTS: POST /favorite/{media_id}
# =============================================================================

class TestToggleFavorite:
    """Tests de POST /api/favorite/{media_id}"""
    
    @pytest.mark.asyncio
    async def test_add_favorite(self, client, mock_plex_client):
        """Test ajout aux favoris"""
        mock_plex_client.mark_as_favorite = AsyncMock(return_value=True)
        
        response = client.post("/api/favorite/tt1375666")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "favoris" in data["message"].lower()

    @pytest.mark.asyncio
    async def test_add_favorite_failure(self, client, mock_plex_client):
        """Test échec ajout aux favoris"""
        mock_plex_client.mark_as_favorite = AsyncMock(return_value=False)
        
        response = client.post("/api/favorite/tt1375666")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

# =============================================================================
# TESTS: POST /rate/{media_id}/{rating}
# =============================================================================

class TestRateMedia:
    """Tests de POST /api/rate/{media_id}/{rating}"""
    
    @pytest.mark.asyncio
    async def test_rate_media_valid(self, client, mock_plex_client):
        """Test notation valide"""
        mock_plex_client.rate_media = AsyncMock(return_value=True)
        
        response = client.post("/api/rate/tt1375666/8.5")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_rate_media_invalid_high(self, client):
        """Test notation trop élevée"""
        response = client.post("/api/rate/tt1375666/11")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_rate_media_invalid_low(self, client):
        """Test notation négative"""
        response = client.post("/api/rate/tt1375666/-1")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

    @pytest.mark.asyncio
    async def test_rate_media_zero(self, client, mock_plex_client):
        """Test notation zéro (dé-noter)"""
        mock_plex_client.rate_media = AsyncMock(return_value=True)
        
        response = client.post("/api/rate/tt1375666/0")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

# =============================================================================
# TESTS: POST /label/{media_id}/{label}
# =============================================================================

class TestAddLabel:
    """Tests de POST /api/label/{media_id}/{label}"""
    
    @pytest.mark.asyncio
    async def test_add_label_success(self, client, mock_plex_client):
        """Test ajout label avec succès"""
        mock_plex_client.add_label = AsyncMock(return_value=True)
        
        response = client.post("/api/label/tt1375666/Watchlist")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "Watchlist" in data["message"]

    @pytest.mark.asyncio
    async def test_add_label_failure(self, client, mock_plex_client):
        """Test échec ajout label"""
        mock_plex_client.add_label = AsyncMock(return_value=False)
        
        response = client.post("/api/label/tt1375666/CustomLabel")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

# =============================================================================
# TESTS: DELETE /label/{media_id}/{label}
# =============================================================================

class TestRemoveLabel:
    """Tests de DELETE /api/label/{media_id}/{label}"""
    
    @pytest.mark.asyncio
    async def test_remove_label_success(self, client, mock_plex_client):
        """Test suppression label avec succès"""
        mock_plex_client.remove_label = AsyncMock(return_value=True)
        
        response = client.delete("/api/label/tt1375666/Watchlist")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"

    @pytest.mark.asyncio
    async def test_remove_label_not_found(self, client, mock_plex_client):
        """Test suppression label inexistant"""
        mock_plex_client.remove_label = AsyncMock(return_value=False)
        
        response = client.delete("/api/label/tt1375666/NonExistent")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

# =============================================================================
# TESTS: POST /optimize/{media_id}
# =============================================================================

class TestOptimizeMedia:
    """Tests de POST /api/optimize/{media_id}"""
    
    @pytest.mark.asyncio
    async def test_optimize_media_mobile(self, client, mock_plex_client):
        """Test optimisation pour mobile"""
        mock_plex_client.optimize_media = AsyncMock(return_value=True)
        
        response = client.post("/api/optimize/tt1375666?target=mobile")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "mobile" in data["message"]

    @pytest.mark.asyncio
    async def test_optimize_media_default(self, client, mock_plex_client):
        """Test optimisation avec cible par défaut"""
        mock_plex_client.optimize_media = AsyncMock(return_value=True)
        
        response = client.post("/api/optimize/tt1375666")
        
        assert response.status_code == 200
        mock_plex_client.optimize_media.assert_called_with("tt1375666", target="mobile")

    @pytest.mark.asyncio
    async def test_optimize_media_failure(self, client, mock_plex_client):
        """Test échec optimisation"""
        mock_plex_client.optimize_media = AsyncMock(return_value=False)
        
        response = client.post("/api/optimize/tt1375666")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "error"

# =============================================================================
# TESTS: CACHE ENDPOINTS
# =============================================================================

class TestCacheEndpoints:
    """Tests des endpoints de gestion du cache"""
    
    def test_cache_stats_empty(self, client):
        """Test récupération stats cache vide"""
        response = client.get("/api/cache/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert "cache_stats" in data
        assert "timestamp" in data

    def test_cache_clear(self, client):
        """Test nettoyage du cache"""
        response = client.post("/api/cache/clear")
        
        assert response.status_code == 200
        data = response.json()
        assert "cleared" in data["status"].lower()

# =============================================================================
# TESTS: REFRESH ENDPOINT
# =============================================================================

class TestRefreshEndpoint:
    """Tests de POST /api/refresh"""
    
    def test_refresh_triggered(self, client, mock_plex_client):
        """Test déclenchement scan manuel"""
        mock_plex_client.is_scanning = False
        mock_plex_client.refresh_library = AsyncMock()
        
        response = client.post("/api/refresh")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "accepted"

    def test_refresh_already_scanning(self, client, mock_plex_client):
        """Test quand scan déjà en cours"""
        mock_plex_client.is_scanning = True
        
        response = client.post("/api/refresh")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "busy"
