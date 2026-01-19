# 🧪 Guide Complet des Tests PlexHub

## 📦 Installation

### 1. Installer les dépendances de test
```bash
pip install -r requirements-test.txt
```

Ou à minima:
```bash
pip install pytest pytest-asyncio pytest-cov
```

### 2. Vérifier l'installation
```bash
pytest --version
# pytest 7.x.x
```

## 🚀 Exécution des Tests

### Mode Rapide (Tests unitaires)
```bash
pytest tests/ -m "not slow"
```

### Tous les tests
```bash
pytest tests/
```

### Avec rapport de couverture
```bash
pytest tests/ --cov=app --cov-report=html
open htmlcov/index.html
```

### Tests spécifiques par fichier

#### Endpoints REST
```bash
pytest tests/test_api_endpoints.py -v
```

#### Films/Séries
```bash
pytest tests/test_api_movies.py -v
```

#### Streaming & Images
```bash
pytest tests/test_api_streaming.py -v
```

#### Intégration
```bash
pytest tests/test_integration.py -v
```

### Tests spécifiques par classe
```bash
# Seulement GetServers
pytest tests/test_api_endpoints.py::TestGetServers -v

# Seulement un test
pytest tests/test_api_endpoints.py::TestGetServers::test_get_servers_success -v
```

## 📊 Résultats Attendus

### Sans couverture (~30 secondes)
```
tests/test_api_endpoints.py ............................ [ 10%]
tests/test_api_movies.py ............................... [ 40%]
tests/test_api_streaming.py ............................ [ 65%]
tests/test_integration.py .............................. [ 95%]

====== 150+ passed in 30.42s ======
```

### Avec couverture (~40 secondes)
```
Name                    Stmts   Miss  Cover
---------------------------------------------
app/main.py               285     20    93%
app/plex_client.py        156     12    92%
app/models.py              89      5    94%
app/config.py              25      2    92%
---------------------------------------------
TOTAL                     555     39    93%

====== 150+ passed in 40.15s ======
```

## 🎯 Patterns de Test Utilisés

### 1. Pattern Mock-Based (le plus courant)
```python
def test_get_movies_success(self, client, mock_plex_client):
    """Test avec mock du PlexClient"""
    mock_plex_client.get_movies = MagicMock(return_value=[...])
    
    response = client.get("/api/movies")
    
    assert response.status_code == 200
    mock_plex_client.get_movies.assert_called_once()
```

**Cas d'usage:**
- Tests d'endpoints (requête HTTP)
- Isolation de la logique métier
- Vérification appels aux dépendances

### 2. Pattern Fixture-Based
```python
@pytest.fixture
def sample_movie_detail():
    """Données réutilisables pour tests"""
    return MovieDetail(
        id="tt1375666",
        title="Inception",
        ...
    )

def test_with_fixture(self, client, sample_movie_detail):
    # Utiliser sample_movie_detail
    pass
```

**Cas d'usage:**
- Données complexes réutilisées
- Setup/teardown commun
- Réduction de duplication

### 3. Pattern Async Mock
```python
@pytest.mark.asyncio
async def test_async_operation(self, client, mock_plex_client):
    """Test avec fonction async mockée"""
    mock_plex_client.get_recently_added = AsyncMock(return_value={})
    
    response = client.get("/api/recently-added")
    
    assert response.status_code == 200
```

**Cas d'usage:**
- Tests d'endpoints qui appellent des functions async
- Simulation de timeouts/erreurs async

### 4. Pattern Context Manager (patch)
```python
def test_with_db_mock(self, client):
    """Test avec mock du chemin BD"""
    with patch('app.main.plex_client.db_path', '/fake/path.db'):
        response = client.get("/api/movies")
```

**Cas d'usage:**
- Remplacer configurations globales
- Tester sans BD réelle
- Isoler système de fichiers

### 5. Pattern Data-Driven (Parametrize)
```python
@pytest.mark.parametrize("media_id,expected", [
    ("tt1375666", 200),
    ("invalid", 404),
])
def test_get_movie_detail(self, client, media_id, expected):
    response = client.get(f"/api/movies/{media_id}")
    assert response.status_code == expected
```

**Cas d'usage:**
- Tester multiples cas
- Réduire duplication
- Validation de frontières

### 6. Pattern Exception Handling
```python
def test_server_error(self, client, mock_plex_client):
    """Test gestion erreurs gracieuses"""
    mock_plex_client.get_movies = MagicMock(
        side_effect=ConnectionError("Plex unreachable")
    )
    
    response = client.get("/api/movies")
    
    assert response.status_code >= 400
```

**Cas d'usage:**
- Vérifier gestion erreurs
- Tester fallback mechanisms
- Resilience testing

## 📋 Checklist Avant Commit

```markdown
- [ ] Tous les tests passent: pytest tests/
- [ ] Couverture >= 90%: pytest tests/ --cov=app
- [ ] Pas de warnings: pytest tests/ -W error
- [ ] Pas de tests slow qui traînent: pytest tests/ -m "not slow"
- [ ] Docstrings sur tous les tests
- [ ] Tests groupés logiquement par classe
- [ ] Mocks correctement nettoyés après test
```

## 🔍 Débogage Avancé

### Voir où le test échoue
```bash
pytest tests/test_api_endpoints.py::TestGetMovies::test_get_movies_default -vv
```

### Avec pdb (debugger interactif)
```bash
pytest tests/test_api_endpoints.py::TestGetMovies::test_get_movies_default --pdb
```

### Voir tous les appels au mock
```python
def test_debug(self, client, mock_plex_client):
    mock_plex_client.get_movies = MagicMock(return_value=[])
    
    response = client.get("/api/movies")
    
    # Voir tous les appels
    print(mock_plex_client.get_movies.call_args_list)
    # [(call(...),), (call(...),)]
```

### Les tests les plus lents
```bash
pytest tests/ --durations=20
```

## 🚨 Problèmes Courants et Solutions

### ❌ "fixture 'mock_plex_client' not found"
```python
# ✅ Solution: La fixture doit être dans conftest.py ou le même fichier
@pytest.fixture
def mock_plex_client():
    with patch('app.main.plex_client') as mock:
        yield mock
```

### ❌ "RuntimeError: asyncio.run() cannot be called from a running event loop"
```python
# ✅ Solution: Utiliser @pytest.mark.asyncio
@pytest.mark.asyncio
async def test_async_endpoint(self, client):
    response = client.get("/api/endpoint")
```

### ❌ Tests qui passent séparé mais échouent ensemble
```python
# ✅ Solution: Utiliser autouse=True pour nettoyer cache avant chaque test
@pytest.fixture(autouse=True)
def clear_cache():
    _api_cache.clear()
    yield
    _api_cache.clear()
```

### ❌ Mock ne retourne rien
```python
# ❌ Mauvais:
mock_plex_client.get_movies = MagicMock()  # Retourne MagicMock()

# ✅ Bon:
mock_plex_client.get_movies = MagicMock(return_value=[])
```

### ❌ Paramètre non passé au mock
```python
# ❌ Mauvais: Assertion sur le mock pas appelé
mock_plex_client.get_movies.assert_called_once()

# ✅ Bon: Vérifier avec les arguments
mock_plex_client.get_movies.assert_called_with(limit=50)
```

## 📈 Améliorer la Couverture

### Identifier les lignes non testées
```bash
pytest tests/ --cov=app --cov-report=term-missing

# Result:
# app/main.py:150    missing
# app/plex_client.py:87    missing
```

### Couvrir les cas d'erreur
```python
# Avant (1 cas):
def test_get_movie(self, client):
    response = client.get("/api/movies/tt1375666")
    assert response.status_code == 200

# Après (3 cas):
def test_get_movie_found(self, client, sample_movie_detail):
    # ... found case

def test_get_movie_not_found(self, client):
    # ... 404 case

def test_get_movie_error(self, client, mock_plex_client):
    # ... error case
```

## 🎨 Best Practices

### 1. Nommer les tests descriptif
```python
# ❌ Mauvais:
def test_1(self, client):
    pass

# ✅ Bon:
def test_get_movies_with_pagination_returns_correct_page_size(self, client):
    pass
```

### 2. Une assertion par test
```python
# ❌ Mauvais: Trop d'assertions mélangées
def test_movies(self, client):
    assert len(data) == 5
    assert data[0]["title"] == "Inception"
    assert data[1]["rating"] == 8.8

# ✅ Bon: Tests séparés et clairs
def test_movies_count(self, client):
    assert len(data) == 5

def test_first_movie_title(self, client):
    assert data[0]["title"] == "Inception"

def test_first_movie_rating(self, client):
    assert data[1]["rating"] == 8.8
```

### 3. Utiliser des messages clairs
```python
# ❌ Mauvais:
assert response.status_code == 200

# ✅ Bon:
assert response.status_code == 200, (
    f"Expected 200, got {response.status_code}. "
    f"Response: {response.json()}"
)
```

### 4. Organiser en classes
```python
# ✅ Bon: Tests groupés par endpoint
class TestGetMovies:
    def test_default_parameters(self): ...
    def test_pagination(self): ...
    def test_filtering(self): ...

class TestGetMovieDetail:
    def test_found(self): ...
    def test_not_found(self): ...
```

## 📞 Commandes Rapides

```bash
# Exécuter & afficher couverture manquante
pytest tests/ --cov=app --cov-report=term-missing

# HTML report
pytest tests/ --cov=app --cov-report=html && open htmlcov/index.html

# Profiler: tests les plus lents
pytest tests/ --durations=10

# Paralléliser (4 workers)
pytest tests/ -n auto

# Arrêter au premier échec
pytest tests/ -x

# Exécuter dernier test échoué
pytest tests/ --lf

# Verbose + show print statements
pytest tests/ -vv -s

# Test un pattern
pytest tests/ -k "recently"  # Tous les tests avec "recently"

# Combiné: Performance + Coverage
pytest tests/ -m "not slow" --cov=app --durations=5
```

## 📚 Ressources

- [pytest documentation](https://docs.pytest.org/)
- [pytest-asyncio](https://github.com/pytest-dev/pytest-asyncio)
- [TestClient documentation](https://fastapi.tiangolo.com/advanced/async-tests/)
- [unittest.mock documentation](https://docs.python.org/3/library/unittest.mock.html)

---

**Version**: 1.0
**Last Updated**: 2026-01-19
**Tests**: 150+
**Coverage Target**: >90%
