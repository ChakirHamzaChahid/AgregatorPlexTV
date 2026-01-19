"""
Tests des endpoints de gestion des films et séries.

Couvre:
- GET /api/movies (Récupération liste avec pagination/filtrage)
- GET /api/movies/{movie_id} (Détails complets d'un média)
"""

import pytest
import sqlite3
import json
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from app.main import app
from app.models import MovieDetail, Source, Season, Episode, Chapter, CastMember

# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def client():
    """Client de test FastAPI"""
    return TestClient(app)

@pytest.fixture
def mock_plex_client():
    """Mock du PlexClient"""
    with patch('app.main.plex_client') as mock:
        yield mock

@pytest.fixture
def sample_movie_detail():
    """Données film complet pour les tests"""
    return MovieDetail(
        id="tt1375666",
        title="Inception",
        type="movie",
        year=2010,
        rating=8.8,
        poster_url="/proxy-image?thumb=/library/metadata/123/thumb",
        backdrop_url="/proxy-image?thumb=/library/metadata/123/art",
        summary="Un voleur doit infiltrer l'esprit de cibles pour voler leurs secrets.",
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
        labels=["Watchlist"],
        chapters=[
            Chapter(
                id="chap-1",
                title="Introduction",
                start_time_ms=0,
                end_time_ms=300000,
                thumb_url="/proxy-image?thumb=/library/metadata/123/chapter/1"
            )
        ],
        cast=[
            CastMember(
                name="Leonardo DiCaprio",
                role="Cobb",
                thumb_url="/proxy-image?thumb=/library/metadata/123/cast/1"
            )
        ],
        sources=[
            Source(
                server_name="Mon Serveur",
                resolution="1080P",
                is_owned=True,
                stream_url="/vlc-stream/tt1375666",
                m3u_url="/playlist/tt1375666.m3u",
                plex_deeplink="plex://preplay/tt1375666"
            ),
            Source(
                server_name="Serveur Ami",
                resolution="4K",
                is_owned=False,
                stream_url="/vlc-stream/tt1375666-friend",
                m3u_url="/playlist/tt1375666-friend.m3u",
                plex_deeplink="plex://preplay/tt1375666"
            )
        ],
        seasons=[]
    )

@pytest.fixture
def sample_series_detail():
    """Données série avec saisons/épisodes pour les tests"""
    return MovieDetail(
        id="tt0944947",
        title="Game of Thrones",
        type="show",
        year=2011,
        rating=9.1,
        poster_url="/proxy-image?thumb=/library/metadata/124/thumb",
        backdrop_url="/proxy-image?thumb=/library/metadata/124/art",
        summary="Un épic fantastique avec politique et dragons.",
        runtime=0,  # Les séries n'ont pas de durée unique
        genres=["Drama", "Fantasy", "Mystery"],
        director="",
        writer="David Benioff, D.B. Weiss",
        content_rating="R",
        studio="HBO",
        added_at=datetime.now(),
        updated_at=datetime.now(),
        watched=False,
        watched_at=None,
        progress_percent=0,
        markers=[],
        labels=[],
        chapters=[],
        cast=[
            CastMember(
                name="Kit Harington",
                role="Jon Snow",
                thumb_url="/proxy-image?thumb=/library/metadata/124/cast/1"
            )
        ],
        sources=[
            Source(
                server_name="Mon Serveur",
                resolution="1080P",
                is_owned=True,
                stream_url="/vlc-stream/tt0944947",
                m3u_url="/playlist/tt0944947.m3u",
                plex_deeplink="plex://preplay/tt0944947"
            )
        ],
        seasons=[
            Season(
                season_number=1,
                title="Season 1",
                episodes=[
                    Episode(
                        episode_number=1,
                        title="Winter is Coming",
                        summary="Ned et sa famille voyagent.",
                        runtime=56,
                        thumb_url="/proxy-image?thumb=/library/metadata/124/season/1/ep/1",
                        sources=[
                            Source(
                                server_name="Mon Serveur",
                                resolution="1080P",
                                is_owned=True,
                                stream_url="/vlc-stream/tt0944947-s1e1",
                                m3u_url="/playlist/tt0944947-s1e1.m3u",
                                plex_deeplink="plex://preplay/tt0944947-s1e1"
                            )
                        ]
                    )
                ]
            )
        ]
    )

@pytest.fixture
def mock_db_with_movies(tmp_path, sample_movie_detail, sample_series_detail):
    """Mock BD SQLite avec données de test"""
    db_path = tmp_path / "test.db"
    
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE media_v2 (
                id TEXT PRIMARY KEY,
                title TEXT,
                type TEXT,
                year INTEGER,
                added_at TIMESTAMP,
                rating REAL,
                data TEXT
            )
        """)
        
        # Insérer films/séries de test
        conn.execute(
            "INSERT INTO media_v2 VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sample_movie_detail.id,
                sample_movie_detail.title,
                sample_movie_detail.type,
                sample_movie_detail.year,
                sample_movie_detail.added_at.isoformat(),
                sample_movie_detail.rating,
                json.dumps(sample_movie_detail.model_dump(mode='json'))
            )
        )
        
        conn.execute(
            "INSERT INTO media_v2 VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                sample_series_detail.id,
                sample_series_detail.title,
                sample_series_detail.type,
                sample_series_detail.year,
                sample_series_detail.added_at.isoformat(),
                sample_series_detail.rating,
                json.dumps(sample_series_detail.model_dump(mode='json'))
            )
        )
    
    return str(db_path)

# =============================================================================
# TESTS: GET /api/movies (LISTING & FILTRAGE)
# =============================================================================

class TestGetMovies:
    """Tests de GET /api/movies"""
    
    def test_get_movies_default(self, client, mock_db_with_movies, sample_movie_detail):
        """Test récupération liste films par défaut"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert data[0]["title"] in [sample_movie_detail.title, sample_series_detail.title]

    def test_get_movies_android_mode_pagination(self, client, mock_db_with_movies):
        """Test mode Android avec pagination (page + size)"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?page=1&size=10")
        
        assert response.status_code == 200
        data = response.json()
        # En mode Android, sources sont vidés
        if len(data) > 0:
            assert data[0]["sources"] == []

    def test_get_movies_web_mode(self, client, mock_db_with_movies):
        """Test mode Web (sans page/size) retourne sources complètes"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies")
        
        assert response.status_code == 200
        data = response.json()
        # En mode Web, sources sont présentes
        if len(data) > 0:
            assert "sources" in data[0]

    def test_get_movies_filter_by_type_movie(self, client, mock_db_with_movies):
        """Test filtrage par type=movie"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?type=movie")
        
        assert response.status_code == 200
        data = response.json()
        # Doit retourner que les films
        for item in data:
            assert item["type"] == "movie"

    def test_get_movies_filter_by_type_show(self, client, mock_db_with_movies):
        """Test filtrage par type=show"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?type=show")
        
        assert response.status_code == 200
        data = response.json()
        # Doit retourner que les séries
        for item in data:
            assert item["type"] == "show"

    def test_get_movies_search_by_title(self, client, mock_db_with_movies):
        """Test recherche par titre"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?search=Inception")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
        assert "Inception" in data[0]["title"]

    def test_get_movies_search_empty_results(self, client, mock_db_with_movies):
        """Test recherche sans résultats"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?search=NonExistentMovie")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 0

    def test_get_movies_sort_by_added_at_desc(self, client, mock_db_with_movies):
        """Test tri par date d'ajout décroissant"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?sort=added_at&order=desc")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

    def test_get_movies_sort_by_title_asc(self, client, mock_db_with_movies):
        """Test tri par titre croissant"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?sort=title&order=asc")
        
        assert response.status_code == 200
        data = response.json()
        # Vérifier que les titres sont triés
        if len(data) > 1:
            assert data[0]["title"] <= data[1]["title"]

    def test_get_movies_sort_by_rating(self, client, mock_db_with_movies):
        """Test tri par rating"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?sort=rating&order=desc")
        
        assert response.status_code == 200
        data = response.json()
        if len(data) > 1:
            assert data[0]["rating"] >= data[1]["rating"]

    def test_get_movies_pagination_page_1(self, client, mock_db_with_movies):
        """Test pagination première page"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?page=1&size=1")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data) <= 1

    def test_get_movies_pagination_page_2(self, client, mock_db_with_movies):
        """Test pagination deuxième page"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?page=2&size=1")
        
        assert response.status_code == 200
        data = response.json()

    def test_get_movies_combined_filters(self, client, mock_db_with_movies):
        """Test combinaison de plusieurs filtres"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies?type=movie&sort=rating&order=desc")
        
        assert response.status_code == 200
        data = response.json()
        for item in data:
            assert item["type"] == "movie"

# =============================================================================
# TESTS: GET /api/movies/{movie_id}
# =============================================================================

class TestGetMovieDetail:
    """Tests de GET /api/movies/{movie_id}"""
    
    def test_get_movie_detail_found(self, client, mock_db_with_movies, sample_movie_detail):
        """Test récupération détails film existant"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_movie_detail.id
        assert data["title"] == sample_movie_detail.title
        assert data["type"] == "movie"

    def test_get_movie_detail_complete_fields(self, client, mock_db_with_movies, sample_movie_detail):
        """Test que tous les champs sont présents"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Champs obligatoires
        assert "id" in data
        assert "title" in data
        assert "type" in data
        assert "year" in data
        assert "rating" in data
        assert "poster_url" in data
        assert "summary" in data
        assert "runtime" in data
        assert "genres" in data
        assert "sources" in data

    def test_get_movie_detail_with_chapters(self, client, mock_db_with_movies, sample_movie_detail):
        """Test films avec chapitres"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "chapters" in data
        if len(data["chapters"]) > 0:
            assert "title" in data["chapters"][0]
            assert "start_time_ms" in data["chapters"][0]

    def test_get_movie_detail_with_cast(self, client, mock_db_with_movies, sample_movie_detail):
        """Test films avec distribution"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "cast" in data
        if len(data["cast"]) > 0:
            assert "name" in data["cast"][0]
            assert "role" in data["cast"][0]

    def test_get_movie_detail_with_multiple_sources(self, client, mock_db_with_movies, sample_movie_detail):
        """Test film avec plusieurs sources (multi-serveur)"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert len(data["sources"]) >= 2
        
        # Vérifier structure sources
        for source in data["sources"]:
            assert "server_name" in source
            assert "resolution" in source
            assert "is_owned" in source
            assert "stream_url" in source

    def test_get_series_detail_with_seasons(self, client, mock_db_with_movies, sample_series_detail):
        """Test série avec saisons et épisodes"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_series_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["type"] == "show"
        assert "seasons" in data
        assert len(data["seasons"]) >= 1
        
        # Vérifier structure saison
        season = data["seasons"][0]
        assert "season_number" in season
        assert "episodes" in season
        assert len(season["episodes"]) >= 1
        
        # Vérifier structure épisode
        episode = season["episodes"][0]
        assert "episode_number" in episode
        assert "title" in episode
        assert "sources" in episode

    def test_get_movie_detail_not_found(self, client, mock_db_with_movies):
        """Test média inexistant"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get("/api/movies/tt9999999")
        
        assert response.status_code == 404

    def test_get_movie_detail_url_reconstruction(self, client, mock_db_with_movies, sample_movie_detail):
        """Test reconstruction URLs absolues"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        
        # Les URLs relatives doivent être reconstruites
        poster = data.get("poster_url", "")
        backdrop = data.get("backdrop_url", "")
        
        # Vérifier que les URLs sont cohérentes
        if poster:
            assert isinstance(poster, str)
        if backdrop:
            assert isinstance(backdrop, str)

    def test_get_movie_detail_with_labels(self, client, mock_db_with_movies, sample_movie_detail):
        """Test film avec labels/tags"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "labels" in data

    def test_get_movie_detail_watched_status(self, client, mock_db_with_movies, sample_movie_detail):
        """Test statut visionnage"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response = client.get(f"/api/movies/{sample_movie_detail.id}")
        
        assert response.status_code == 200
        data = response.json()
        assert "watched" in data
        assert "watched_at" in data
        assert "progress_percent" in data

# =============================================================================
# TESTS: CACHE BEHAVIOR
# =============================================================================

class TestMoviesCaching:
    """Tests du comportement de cache pour /movies"""
    
    def test_movies_cache_hit(self, client, mock_db_with_movies):
        """Test que le cache est utilisé"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            # Première requête
            response1 = client.get("/api/movies?page=1&size=10")
            
            # Deuxième requête identique (doit venir du cache)
            response2 = client.get("/api/movies?page=1&size=10")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        # Les réponses doivent être identiques
        assert response1.json() == response2.json()

    def test_movies_cache_different_params(self, client, mock_db_with_movies):
        """Test que paramètres différents créent entrées cache différentes"""
        with patch('app.main.plex_client.db_path', mock_db_with_movies):
            response1 = client.get("/api/movies?page=1&size=10")
            response2 = client.get("/api/movies?page=2&size=10")
        
        assert response1.status_code == 200
        assert response2.status_code == 200
        # Les réponses peuvent être différentes
        # (dépend du nombre d'items)
