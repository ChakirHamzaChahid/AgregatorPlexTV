# Tests API PlexHub 🧪

Ce répertoire contient une suite complète de tests pour l'API PlexHub.

## 📋 Couverture des Tests

### test_api_endpoints.py
Tests des endpoints REST principaux:
- ✅ GET /servers - Récupération serveurs
- ✅ GET /collections - Récupération collections
- ✅ GET /continue_watching - Médias en cours
- ✅ POST /actions/scrobble - Marquage vu/non-vu
- ✅ POST /actions/progress - Mise à jour progression
- ✅ GET /recently-added - Nouveautés
- ✅ GET /watch-history - Historique enrichi
- ✅ GET /now-playing - Sessions actives
- ✅ GET /clients - Clients Plex
- ✅ GET /hubs - Hubs découverte
- ✅ GET /search - Recherche avancée
- ✅ POST /favorite/{media_id} - Favoris
- ✅ POST /rate/{media_id}/{rating} - Notation
- ✅ POST/DELETE /label/{media_id}/{label} - Labels
- ✅ POST /optimize/{media_id} - Optimisation
- ✅ GET /cache/stats - Statistiques cache
- ✅ POST /cache/clear - Nettoyage cache
- ✅ POST /refresh - Refresh manuel

### test_api_movies.py
Tests des endpoints films/séries:
- ✅ GET /movies - Listing avec pagination/filtrage
  - Filtrage par type (movie/show)
  - Recherche par titre
  - Tri (rating, titre, année, date ajout)
  - Pagination (mode Android vs Web)
  - Cache comportement
- ✅ GET /movies/{movie_id} - Détails complets
  - Reconstruction URLs
  - Chapitres et cast
  - Plusieurs sources multi-serveur
  - Saisons/épisodes pour séries
  - Labels et statut visionnage

### test_api_streaming.py
Tests des endpoints streaming:
- ✅ GET /playlist/{play_id}.m3u - Génération playlist M3U
- ✅ GET /vlc-stream/{play_id} - Streaming vidéo
  - Limitation slots concurrents (sémaphore)
  - Fallback Direct Play si transcode échoue
  - Gestion saturation
- ✅ GET /proxy-image - Proxy & redimensionnement images
  - Redimensionnement optimisé (400px, 1280px)
  - Conversion format (RGBA→RGB, palette→RGB)
  - Cache navigateur long-term
  - Headers CORS
  - Qualité WEBP (quality=80)

### test_integration.py
Tests d'intégration end-to-end:
- ✅ Workflows complets (recherche → lecture)
- ✅ Cache effectiveness
- ✅ Filtrage multi-critères
- ✅ Actions utilisateur (marquer, noter, labéliser)
- ✅ Gestion d'erreur gracieuse
- ✅ Streaming cohérence
- ✅ Discovery & recommendations
- ✅ Perf regression tests

## 🚀 Installation & Configuration

### Prérequis
```bash
pip install pytest pytest-asyncio fastapi pydantic pillow
```

### Structure des tests
```
tests/
├── conftest.py              # Fixtures globales & configuration
├── test_api_endpoints.py    # Tests endpoints REST (18+ classes)
├── test_api_movies.py       # Tests /movies et filtrage (50+ tests)
├── test_api_streaming.py    # Tests streaming & proxy image (35+ tests)
├── test_integration.py      # Tests intégration end-to-end (35+ tests)
└── README.md               # Cette documentation
```

## 📊 Exécution des Tests

### Tous les tests
```bash
pytest tests/
```

### Tests spécifiques
```bash
# Seulement endpoints
pytest tests/test_api_endpoints.py

# Seulement films/séries
pytest tests/test_api_movies.py

# Seulement streaming
pytest tests/test_api_streaming.py

# Seulement intégration
pytest tests/test_integration.py -m integration

# Seulement tests rapides (exclure slow)
pytest tests/ -m "not slow"
```

### Options de filtering avancées
```bash
# Tests avec verbose output
pytest tests/ -v

# Avec couverture de code
pytest tests/ --cov=app --cov-report=html

# Arrêter au premier test échoué
pytest tests/ -x

# Afficher les 10 tests les plus lents
pytest tests/ --durations=10

# Exécuter un test spécifique
pytest tests/test_api_endpoints.py::TestGetServers::test_get_servers_success

# Avec des logs
pytest tests/ -s --log-cli-level=DEBUG
```

### Groupes de tests avec markers
```bash
# Tests asyncio uniquement
pytest tests/ -m asyncio

# Tests d'intégration (nécessitent plus de setup)
pytest tests/ -m integration

# Tests lents (perf regression, stress tests)
pytest tests/ -m slow

# Tout SAUF les tests lents
pytest tests/ -m "not slow"
```

## 🧪 Chaque fichier de test

### test_api_endpoints.py (~400 assertions)

**Classes de test:**
- `TestGetServers` (3 tests)
  - Success avec données
  - Liste vide
  - Error handling

- `TestGetCollections` (2 tests asyncio)
  - Success avec collection
  - Liste vide

- `TestGetContinueWatching` (2 tests asyncio)
  - Avec données
  - Liste vide

- `TestScrobbleAction` (4 tests asyncio)
  - Marquer vu
  - Marquer non-vu
  - Paramètre manquant
  - Échec

- `TestUpdateProgress` (3 tests asyncio)
  - Success
  - Paramètre manquant
  - Échec

- `TestRecentlyAdded` (3 tests asyncio)
  - Par défaut
  - Avec limit custom
  - Liste vide

- `TestWatchHistory` (3 tests asyncio)
  - Par défaut
  - Avec paramètres
  - Liste vide

- `TestNowPlaying` (2 tests asyncio)
  - Avec sessions
  - Aucune session

- `TestGetClients` (2 tests asyncio)
  - Avec clients
  - Aucun client

- `TestGetHubs` (2 tests asyncio)
  - Avec hubs
  - Avec limit custom

- `TestAdvancedSearch` (5 tests asyncio)
  - Par titre
  - Par année
  - Filtre non-vus
  - Avec tri
  - Aucun résultat

- `TestToggleFavorite` (2 tests asyncio)
  - Success
  - Échec

- `TestRateMedia` (4 tests asyncio)
  - Note valide
  - Note trop haute
  - Note négative
  - Zéro (dé-noter)

- `TestAddLabel` (2 tests asyncio)
  - Success
  - Échec

- `TestRemoveLabel` (2 tests asyncio)
  - Success
  - Label inexistant

- `TestOptimizeMedia` (3 tests asyncio)
  - Pour mobile
  - Par défaut
  - Échec

- `TestCacheEndpoints` (2 tests)
  - Stats cache vide
  - Clear cache

- `TestRefreshEndpoint` (2 tests)
  - Refresh déclenché
  - Déjà en cours

### test_api_movies.py (~50+ tests)

**Classes de test:**
- `TestGetMovies` (10+ tests)
  - Mode Android (page+size)
  - Mode Web (sans pagination)
  - Filtrer par type
  - Recherche par titre
  - Tri multi-colonnes
  - Pagination
  - Combinaison filtres
  - Cache behavior

- `TestGetMovieDetail` (10+ tests)
  - Film trouvé
  - Tous les champs présents
  - Avec chapitres
  - Avec cast/distribution
  - Sources multiples
  - Série avec saisons/épisodes
  - Média inexistant
  - Reconstruction URLs
  - Labels
  - Statut visionnage

- `TestMoviesCaching` (2 tests)
  - Cache hit
  - Différents paramètres

### test_api_streaming.py (~35+ tests)

**Classes de test:**
- `TestPlaylistEndpoint` (4 tests)
  - Génération basique
  - Encodage URLs
  - Avec token
  - Construction URL

- `TestStreamingEndpoint` (10+ tests)
  - Initialisation
  - Headers
  - Sémaphore protection
  - Saturation handling
  - Transcode vs Direct
  - Fallback
  - Direct Play
  - Paramètres invalides

- `TestProxyImageEndpoint` (15+ tests)
  - Cached image
  - Resize 400px
  - Resize 1280px (backdrop)
  - RGBA conversion
  - Palette conversion
  - Image manquante
  - URL construction
  - WEBP output
  - Quality settings
  - Browser cache headers
  - CORS headers
  - Error handling
  - Width cache invalidation

### test_integration.py (~35+ tests)

**Classes de test:**
- `TestCompleteWatchflow` (3 tests)
  - Search → Detail → Play
  - Continue watching
  - Recently added → Favorite → Rate

- `TestCacheIntegration` (3 tests)
  - Cache effectiveness
  - Differentiation paramètres
  - Clear operation

- `TestSearchAndFilterIntegration` (2 tests)
  - Multi-filter
  - Type filtering

- `TestUserActionsIntegration` (2 tests)
  - Watched + progress
  - Label workflow

- `TestErrorHandlingIntegration` (3 tests)
  - Timeout graceful
  - Invalid ID
  - Server unavailable

- `TestStreamingIntegration` (2 tests)
  - Playlist & stream consistency
  - Concurrent requests

- `TestDiscoveryIntegration` (2 tests)
  - Hubs workflow
  - Collections

- `TestSyncAndUpdatesIntegration` (2 tests)
  - Library refresh
  - Watch history sync

- `TestPerformanceRegression` (2 tests)
  - Large list performance
  - Search performance

## 📈 Métriques

### Couverture
- **Endpoints API**: 18+ routes testées
- **Cas de test**: 150+ assertions
- **Fixtures**: 15+ fixtures réutilisables
- **Mocks**: Couverture complète des dépendances

### Performance
- Tests rapides: ~100ms chacun
- Tests intégration: ~500ms chacun
- Suite complète: ~30 secondes

## 🔧 Débogages

### Voir les logs détaillés
```bash
pytest tests/test_api_endpoints.py::TestGetServers::test_get_servers_success -s
```

### Debugger un test
```bash
pytest tests/test_api_endpoints.py::TestGetServers::test_get_servers_success -vv --pdb
```

### Générer rapport couverture
```bash
pytest tests/ --cov=app --cov-report=html
# Ouvre htmlcov/index.html
```

## 🛠️ Ajouter de nouveaux tests

### Template pour test d'endpoint
```python
class TestNewEndpoint:
    """Tests de GET /api/new-endpoint"""
    
    def test_new_endpoint_success(self, client, mock_plex_client):
        """Test cas succès"""
        mock_plex_client.some_method = MagicMock(return_value=expected_data)
        
        response = client.get("/api/new-endpoint")
        
        assert response.status_code == 200
        assert response.json()["key"] == "value"
    
    def test_new_endpoint_error(self, client, mock_plex_client):
        """Test cas erreur"""
        mock_plex_client.some_method = MagicMock(side_effect=Exception())
        
        response = client.get("/api/new-endpoint")
        
        assert response.status_code >= 400
```

### Bonnes pratiques
1. Utiliser les fixtures fournis dans `conftest.py`
2. Mocker les appels externes (Plex API, DB)
3. Tester succès + erreurs
4. Utiliser descriptive assertion messages
5. Organiser en classes par endpoint
6. Utiliser markers (@pytest.mark.asyncio, @pytest.mark.integration)

## 📝 Continuous Integration

### Fichier GitHub Actions (exemple)
```yaml
name: Tests API
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: actions/setup-python@v2
        with:
          python-version: '3.11'
      - run: pip install -r requirements.txt pytest pytest-asyncio
      - run: pytest tests/ --cov=app
```

## 🐛 Problèmes courants

### "No module named 'app'"
```bash
cd /chemin/vers/AgregatorPlexTV
pytest tests/
```

### Tests asyncio ne s'exécutent pas
```bash
# Assurer pytest-asyncio installé
pip install pytest-asyncio
```

### Timeout sur tests
```bash
pytest tests/ --timeout=10
```

### Fixture non trouvée
- Vérifier qu'elle est dans `conftest.py`
- Vérifier le scope (session, function)
- Vérifier les dépendances de fixture

## 📞 Support

Pour ajouter des tests pour new endpoints:
1. Identifier classe/test existante similaire
2. Dupliquer et adapter
3. Exécuter: `pytest tests/test_new_file.py -v`
4. Vérifier couverture: `pytest tests/ --cov=app`

---

**Last updated**: 2026-01-19
**Total tests**: 150+
**Coverage**: API endpoints & workflows
