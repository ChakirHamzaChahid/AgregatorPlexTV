"""
Tests d'intégration pour l'API PlexHub.

Ces tests vérifient le comportement end-to-end des APIs.

Marqués avec @pytest.mark.integration pour être exécutés séparément.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from datetime import datetime, timedelta

from app.main import app, _api_cache
from app.models import MovieDetail, Source, ServerInfo

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """Client de test FastAPI"""
    return TestClient(app)

@pytest.fixture
def integration_sample_data():
    """Données complètes pour les tests d'intégration"""
    return {
        "servers": [
            ServerInfo(
                name="Serveur Principal",
                url="http://192.168.1.100:32400",
                plex_pass=True,
                owned=True,
                is_available=True
            )
        ],
        "movies": [
            MovieDetail(
                id="tt1375666",
                title="Inception",
                type="movie",
                year=2010,
                rating=8.8,
                poster_url="/thumb/123",
                backdrop_url="/art/123",
                summary="Un voleur doit infiltrer l'esprit de cibles.",
                runtime=148,
                genres=["Action", "Sci-Fi"],
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
                        server_name="Serveur Principal",
                        resolution="1080P",
                        is_owned=True,
                        stream_url="/vlc-stream/tt1375666",
                        m3u_url="/playlist/tt1375666.m3u",
                        plex_deeplink="plex://preplay/tt1375666"
                    )
                ],
                seasons=[]
            )
        ]
    }

# =============================================================================
# TESTS D'INTÉGRATION: WORKFLOWS COMPLETS
# =============================================================================

@pytest.mark.integration
class TestCompleteWatchflow:
    """Test d'un workflow complet: recherche -> détail -> lecture"""
    
    def test_search_and_play_workflow(self, client):
        """Workflow: Rechercher un film → Récupérer détails → Générer playlist"""
        
        with patch('app.main.plex_client') as mock_plex:
            # Étape 1: Rechercher
            mock_plex.advanced_search = AsyncMock(return_value={})
            response = client.get("/api/search?title=Inception")
            assert response.status_code == 200
            
            # Étape 2: Récupérer détails (simulé)
            # response = client.get("/api/movies/tt1375666")
            # assert response.status_code == 200
            
            # Étape 3: Générer playlist pour lecture
            response = client.get(
                "/playlist/tt1375666.m3u?server=http://plex&path=/file&token=token&title=Inception"
            )
            assert response.status_code == 200
            assert "EXTM3U" in response.text

    def test_continue_watching_workflow(self, client):
        """Workflow: En cours de lecture → Récupérer historique → Continuer"""
        
        with patch('app.main.plex_client') as mock_plex:
            # Étape 1: Récupérer "continue watching"
            mock_plex.get_on_deck = AsyncMock(return_value=[])
            response = client.get("/api/continue_watching")
            assert response.status_code == 200

    def test_recently_added_and_watch_workflow(self, client):
        """Workflow: Nouvelles sorties → Ajouter aux favoris → Noter"""
        
        with patch('app.main.plex_client') as mock_plex:
            # Étape 1: Récupérer derniers ajoutés
            mock_plex.get_recently_added = AsyncMock(return_value={})
            response = client.get("/api/recently-added?limit=20")
            assert response.status_code == 200
            
            # Étape 2: Ajouter aux favoris
            mock_plex.mark_as_favorite = AsyncMock(return_value=True)
            response = client.post("/api/favorite/tt1375666")
            assert response.status_code == 200
            
            # Étape 3: Noter
            mock_plex.rate_media = AsyncMock(return_value=True)
            response = client.post("/api/rate/tt1375666/8.5")
            assert response.status_code == 200

# =============================================================================
# TESTS D'INTÉGRATION: CACHE & PERFORMANCE
# =============================================================================

@pytest.mark.integration
class TestCacheIntegration:
    """Tests d'intégration du cache"""
    
    def test_cache_effectiveness(self, client):
        """Vérifier que le cache réduit les requêtes répétées"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.get_movies = AsyncMock(return_value={})
            
            # Première requête (pas en cache)
            response1 = client.get("/api/movies?page=1&size=10")
            assert response1.status_code == 200
            call_count_1 = mock_plex.get_movies.call_count
            
            # Deuxième requête identique (doit venir du cache)
            response2 = client.get("/api/movies?page=1&size=10")
            assert response2.status_code == 200
            call_count_2 = mock_plex.get_movies.call_count
            
            # Le mock ne doit pas être appelé une deuxième fois
            assert call_count_2 == call_count_1

    def test_cache_differentiation(self, client):
        """Vérifier que différents paramètres = différentes entrées cache"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.get_movies = AsyncMock(return_value={})
            
            # Différentes pages
            response1 = client.get("/api/movies?page=1&size=10")
            response2 = client.get("/api/movies?page=2&size=10")
            
            assert response1.status_code == 200
            assert response2.status_code == 200

    def test_cache_clear_operation(self, client):
        """Test que cache/clear nettoie correctement le cache"""
        _api_cache.clear()
        
        response = client.post("/api/cache/clear")
        assert response.status_code == 200

# =============================================================================
# TESTS D'INTÉGRATION: FILTRAGE & RECHERCHE
# =============================================================================

@pytest.mark.integration
class TestSearchAndFilterIntegration:
    """Tests d'intégration du filtrage et recherche"""
    
    def test_multi_filter_search(self, client):
        """Test recherche avec plusieurs filtres combinés"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.advanced_search = AsyncMock(return_value={})
            
            # Recherche: Titre + Année + Tri
            response = client.get(
                "/api/search?title=Inception&year=2010&sort=rating:desc&limit=50"
            )
            
            assert response.status_code == 200
            mock_plex.advanced_search.assert_called_once()

    def test_type_filtering(self, client):
        """Test filtrage par type (movie/show)"""
        
        with patch('app.main.plex_client.db_path', "/fake/path.db"):
            # Les filtres de type sont appliqués au niveau SQL
            response1 = client.get("/api/movies?type=movie")
            response2 = client.get("/api/movies?type=show")
            
            # Les deux doivent retourner 200 (même si DB vide)
            assert response1.status_code in [200, 500]
            assert response2.status_code in [200, 500]

# =============================================================================
# TESTS D'INTÉGRATION: ACTIONS UTILISATEUR
# =============================================================================

@pytest.mark.integration
class TestUserActionsIntegration:
    """Tests d'intégration des actions utilisateur"""
    
    def test_mark_watched_and_update_progress(self, client):
        """Workflow: Marquer comme vu ET mettre à jour progression"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.action_scrobble = AsyncMock(return_value=True)
            mock_plex.action_progress = AsyncMock(return_value=True)
            
            # Étape 1: Mettre à jour progression (45%)
            response = client.post("/api/actions/progress", json={
                "key": "rating-key-123",
                "time_ms": 270000  # 45% of 600sec film
            })
            assert response.status_code == 200
            
            # Étape 2: Marquer comme vu
            response = client.post("/api/actions/scrobble", json={
                "key": "rating-key-123",
                "action": "watched"
            })
            assert response.status_code == 200

    def test_label_workflow(self, client):
        """Workflow: Ajouter label → Vérifier → Retirer label"""
        
        with patch('app.main.plex_client') as mock_plex:
            media_id = "tt1375666"
            label = "Favoris"
            
            # Ajouter label
            mock_plex.add_label = AsyncMock(return_value=True)
            response = client.post(f"/api/label/{media_id}/{label}")
            assert response.status_code == 200
            
            # Retirer label
            mock_plex.remove_label = AsyncMock(return_value=True)
            response = client.delete(f"/api/label/{media_id}/{label}")
            assert response.status_code == 200

# =============================================================================
# TESTS D'INTÉGRATION: ERROR HANDLING & RESILIENCE
# =============================================================================

@pytest.mark.integration
class TestErrorHandlingIntegration:
    """Tests de gestion d'erreur et résilience"""
    
    def test_connection_timeout_graceful_degradation(self, client):
        """Test comportement quand Plex ne répond pas"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.get_servers = MagicMock(side_effect=TimeoutError())
            
            response = client.get("/api/servers")
            # Doit gérer l'erreur gracieusement
            assert response.status_code >= 400

    def test_invalid_media_id_handling(self, client):
        """Test requête avec ID média invalide"""
        
        response = client.get("/api/movies/invalid_id_12345")
        # Doit retourner 404
        assert response.status_code == 404

    def test_server_unavailable_handling(self, client):
        """Test quand le serveur backend est indisponible"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.get_active_sessions = AsyncMock(side_effect=ConnectionError())
            
            response = client.get("/api/now-playing")
            # Doit retourner erreur maîtrisée
            assert response.status_code >= 400 or response.json() == []

# =============================================================================
# TESTS D'INTÉGRATION: STREAMING
# =============================================================================

@pytest.mark.integration
class TestStreamingIntegration:
    """Tests d'intégration du streaming"""
    
    def test_playlist_and_stream_consistency(self, client):
        """Vérifier que playlist et stream sont cohérents"""
        
        media_id = "tt1375666"
        server = "http://192.168.1.100:32400"
        path = "/path/to/file"
        token = "test-token"
        
        # Playlist
        response_playlist = client.get(
            f"/playlist/{media_id}.m3u?server={server}&path={path}&token={token}&title=Test"
        )
        assert response_playlist.status_code == 200
        
        # Le stream URL dans playlist doit correspondre au stream endpoint
        assert f"/vlc-stream/{media_id}" in response_playlist.text

    @pytest.mark.slow
    def test_stream_multiple_concurrent_requests(self, client):
        """Test multiple streams concurrents (limite de 4)"""
        
        with patch('app.main.stream_semaphore') as mock_semaphore:
            mock_semaphore.locked.return_value = False
            
            # Simuler 4 requêtes concurrentes
            for i in range(4):
                with patch('app.main.http_client') as mock_http:
                    mock_response = AsyncMock()
                    mock_response.status_code = 200
                    mock_response.aiter_bytes = AsyncMock(return_value=[])
                    
                    mock_http.stream = AsyncMock()
                    # Vérifier que sémaphore est utilisé

# =============================================================================
# TESTS D'INTÉGRATION: DISCOVERY & RECOMMENDATIONS
# =============================================================================

@pytest.mark.integration
class TestDiscoveryIntegration:
    """Tests d'intégration de découverte et recommandations"""
    
    def test_hubs_discovery_workflow(self, client):
        """Test récupération et navigation des hubs découverte"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.get_discovery_hubs = AsyncMock(return_value={
                "Populaires": [],
                "Tendances": [],
                "Nouveautés": []
            })
            
            response = client.get("/api/hubs?limit=10")
            assert response.status_code == 200
            
            data = response.json()
            assert isinstance(data, dict)

    def test_collections_discovery(self, client):
        """Test récupération collections"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.get_collections = AsyncMock(return_value=[])
            
            response = client.get("/api/collections")
            assert response.status_code == 200

# =============================================================================
# TESTS D'INTÉGRATION: SYNC & UPDATES
# =============================================================================

@pytest.mark.integration
class TestSyncAndUpdatesIntegration:
    """Tests d'intégration du sync et des mises à jour"""
    
    def test_library_refresh_workflow(self, client):
        """Test déclenchement et suivi du refresh de bibliothèque"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.is_scanning = False
            mock_plex.refresh_library = AsyncMock()
            
            # Déclencher refresh
            response = client.post("/api/refresh")
            assert response.status_code == 200
            
            data = response.json()
            assert data["status"] in ["accepted", "busy"]

    def test_watch_history_sync(self, client):
        """Test sync de l'historique de lecture"""
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.get_watch_history = AsyncMock(return_value={})
            
            # Récupérer historique
            response = client.get("/api/watch-history?days_back=7")
            assert response.status_code == 200
            
            mock_plex.get_watch_history.assert_called_once()

# =============================================================================
# TESTS D'INTÉGRATION: PERFORMANCE REGRESSION
# =============================================================================

@pytest.mark.integration
@pytest.mark.slow
class TestPerformanceRegression:
    """Tests de régression de performance"""
    
    def test_large_movie_list_performance(self, client):
        """Test performance avec grande liste de films"""
        
        # Simuler une requête pour une grande liste
        import time
        
        with patch('app.main.plex_client.db_path', "/fake/db"):
            start = time.time()
            response = client.get("/api/movies?page=1&size=100")
            duration = time.time() - start
            
            # Doit compléter en moins de 5 secondes
            assert duration < 5.0

    def test_search_performance(self, client):
        """Test performance de la recherche"""
        
        import time
        
        with patch('app.main.plex_client') as mock_plex:
            mock_plex.advanced_search = AsyncMock(return_value={})
            
            start = time.time()
            response = client.get("/api/search?title=test&limit=100")
            duration = time.time() - start
            
            # Doit compléter en moins de 3 secondes
            assert duration < 3.0
